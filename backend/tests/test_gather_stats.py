import time
from pathlib import Path

from netpulse import __version__
from netpulse.analysis.verdict import conclude
from netpulse.api import queries
from netpulse.db.models import DataVersion, Network, PingRaw, TcpConnect
from netpulse.db.session import get_session, init_engine


def _ping(ts: float, target: str, rtt: float, loss: float = 0.0) -> PingRaw:
    return PingRaw(ts=ts, target=target, loss_pct=loss, rtt_avg=rtt, rtt_min=rtt - 1, jitter=1.0)


def _tcp(ts: float, target: str, status: str) -> TcpConnect:
    ms = 20.0 if status == "ok" else None
    return TcpConnect(ts=ts, target=target, port=443, connect_ms=ms, status=status)


def test_local_attribution_uses_best_path_not_pooled(tmp_path: Path) -> None:
    # The gateway jitters (WiFi spikes 2->60 ms); every internet path carries that same jitter, and
    # a far host sits at a high baseline (150 ms). Pooling targets would read the 135 ms baseline
    # gap as "internet jitter" and wrongly blame the ISP; per-target-best must see the shared
    # first-hop jitter and attribute to LOCAL.
    init_engine(tmp_path / "gs_la.db")
    now = time.time()
    with get_session() as s:
        net = Network(
            key="k", ssid="w", gateway_ip="192.168.1.254", label="w",
            first_seen=now, last_seen=now,
        )
        s.add(net)
        s.flush()
        nid = net.id
        for i in range(40):
            t = now - i * 3
            spike = i % 3 == 0
            rows = [
                _ping(t, "192.168.1.254", 60.0 if spike else 2.0),  # gateway (WiFi) jitter
                _ping(t, "8.8.8.8", 73.0 if spike else 15.0),       # near path, same jitter
                _ping(t, "131.153.11.143", 208.0 if spike else 150.0),  # far path, same jitter
            ]
            for r in rows:
                r.network_id = nid
            s.add_all(rows)
        s.commit()
    with get_session() as s:
        stats = queries.gather_stats(s, window=6 * 3600, window_label="", network_id=nid)
    assert stats.local_attribution is not None
    assert stats.local_attribution.layer == "local"  # not fooled by the far host's baseline


def test_latency_is_per_target_not_pooled(tmp_path: Path) -> None:
    # A distant-but-healthy work host (150 ms) must NOT drag "internet latency" up: the two nearby
    # resolvers (15/18 ms) make the representative latency ~18 ms, not the pooled ~150 ms tail.
    init_engine(tmp_path / "gs.db")
    now = time.time()
    with get_session() as s:
        for i in range(30):
            t = now - i * 3
            s.add_all([
                _ping(t, "8.8.8.8", 15.0),
                _ping(t, "9.9.9.9", 18.0),
                _ping(t, "131.153.11.143", 150.0),  # distant work host
            ])
        s.commit()
    with get_session() as s:
        stats = queries.gather_stats(s, window=6 * 3600, window_label="", network_id=None)
    assert stats.latency is not None and stats.latency < 50  # representative, not the 150 ms tail
    assert stats.latency_excess is not None and stats.latency_excess < 10  # per-target floor


def test_grade_loss_is_average_not_p95_of_quantized_loss(tmp_path: Path) -> None:
    # A target clean on average but with occasional full-drop cycles must be graded on its ~2%
    # AVERAGE loss, not a p95 that quantizes to ~33% and slams the grade to F.
    init_engine(tmp_path / "gs2.db")
    now = time.time()
    with get_session() as s:
        for i in range(60):
            t = now - i * 3
            loss = 33.3 if i % 30 == 0 else 0.0  # ~3% of cycles drop
            s.add(_ping(t, "8.8.8.8", 16.0, loss=loss))
            s.add(_ping(t, "9.9.9.9", 18.0))
        s.commit()
    with get_session() as s:
        stats = queries.gather_stats(s, window=6 * 3600, window_label="", network_id=None)
    assert stats.loss is not None and stats.loss < 5  # the average, not the ~33% p95
    assert conclude(stats).score.grade != "F"


def test_grade_ignores_icmp_loss_when_tcp_forward_path_is_clean(tmp_path: Path) -> None:
    # ICMP reports heavy loss (rate-limiting), but every TCP handshake succeeds → the real forward
    # path is clean, so the grade must NOT be dragged to F by the ICMP artifact. The ICMP figure is
    # still reported as typical_loss for findings.
    init_engine(tmp_path / "gs_fl_ok.db")
    now = time.time()
    with get_session() as s:
        for i in range(60):
            t = now - i * 3
            s.add(_ping(t, "1.1.1.1", 48.0, loss=20.0))  # ICMP rate-limit "loss"
            s.add(_ping(t, "9.9.9.9", 16.0, loss=0.0))
        for i in range(30):  # TCP handshakes all succeed → forward loss 0
            t = now - i * 15
            s.add_all([_tcp(t, "1.1.1.1", "ok"), _tcp(t, "9.9.9.9", "ok")])
        s.commit()
    with get_session() as s:
        stats = queries.gather_stats(s, window=6 * 3600, window_label="", network_id=None)
    assert stats.typical_loss is not None and stats.typical_loss >= 5  # ICMP still surfaced
    assert stats.loss is not None and stats.loss < 2  # grade uses the clean TCP forward path
    assert conclude(stats).score.grade != "F"


def test_grade_drops_when_tcp_forward_path_really_fails(tmp_path: Path) -> None:
    # Genuine forward-path loss: a fifth of TCP handshakes time out. That IS real, so the grade
    # must reflect it (not be excused as an ICMP artifact).
    init_engine(tmp_path / "gs_fl_bad.db")
    now = time.time()
    with get_session() as s:
        for i in range(60):
            s.add(_ping(now - i * 3, "1.1.1.1", 48.0, loss=0.0))  # ICMP looks clean here
        for i in range(40):
            t = now - i * 15
            status = "filtered" if i % 5 == 0 else "ok"  # ~20% real forward loss
            s.add(_tcp(t, "1.1.1.1", status))
        s.commit()
    with get_session() as s:
        stats = queries.gather_stats(s, window=6 * 3600, window_label="", network_id=None)
    assert stats.loss is not None and stats.loss >= 15  # forward loss surfaced to the grade
    assert conclude(stats).score.grade == "F"


def test_grade_excludes_untrusted_version_rows(tmp_path: Path) -> None:
    # A trusted target is clean; an untrusted (0.0.0) target shows heavy loss in the SAME window.
    # With no registry row there is no time cap, so only the code_version filter can exclude the bad
    # rows — the grade must be computed on the trusted data alone.
    init_engine(tmp_path / "gs_trust.db")
    now = time.time()
    with get_session() as s:
        for i in range(60):
            t = now - i * 3
            s.add(_ping(t, "1.1.1.1", 48.0, loss=0.0))  # current version (trusted), clean
            bad = _ping(t, "9.9.9.9", 16.0, loss=50.0)  # heavy loss...
            bad.code_version = "0.0.0"  # ...but untrusted
            s.add(bad)
        s.commit()
    with get_session() as s:
        stats = queries.gather_stats(s, window=6 * 3600, window_label="", network_id=None)
    assert stats.typical_loss is not None and stats.typical_loss < 5  # 0.0.0 50%-loss excluded
    assert conclude(stats).score.grade != "F"


def test_grade_window_capped_to_trusted_start(tmp_path: Path) -> None:
    # The registry marks trusted collection as starting 10 min ago. Data measured BEFORE that — even
    # stamped a trusted version — is from a superseded regime and must not enter the grade. Only the
    # window cap (not the row filter) can exclude it here, since both batches carry __version__.
    init_engine(tmp_path / "gs_cap.db")
    now = time.time()
    with get_session() as s:
        s.add(DataVersion(version=__version__, first_seen_ts=now - 600))
        for i in range(60):  # inside the trusted span (last 10 min), clean
            s.add(_ping(now - i * 3, "1.1.1.1", 48.0, loss=0.0))
        for i in range(60):  # older than the trusted start, heavy loss
            s.add(_ping(now - 3600 - i * 3, "1.1.1.1", 48.0, loss=50.0))
        s.commit()
    with get_session() as s:
        stats = queries.gather_stats(s, window=6 * 3600, window_label="", network_id=None)
    assert stats.typical_loss is not None and stats.typical_loss < 5  # pre-trusted-start excluded
    assert conclude(stats).score.grade != "F"
