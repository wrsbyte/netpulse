from netpulse.analysis.verdict import WindowStats, conclude
from netpulse.analysis.wifi_channel import ChannelAdvice


def test_healthy_window_reports_ok() -> None:
    v = conclude(WindowStats(
        loss=0, latency=25, jitter=2, bufferbloat=4, availability=100,
        wifi_signal_avg=-45, window_label="in the last 24h",
    ))
    assert v.findings[0].severity == "ok"
    assert "healthy" in v.headline.lower()
    assert v.score.grade in ("A", "A+")


def test_outage_is_error_and_attributed_to_isp() -> None:
    v = conclude(WindowStats(
        loss=15, latency=140, jitter=20, bufferbloat=10, availability=95,
        outage_count=3, downtime_s=720, worst_outage_s=300, worst_outage_cause="isp",
        worst_target=("1.1.1.1", 15.0), wifi_signal_avg=-40,
    ))
    top = v.findings[0]
    assert top.severity == "error"
    assert "ISP" in top.detail
    assert v.findings[0].severity == "error"


def test_weak_wifi_flagged_and_drives_attribution() -> None:
    v = conclude(WindowStats(
        loss=5, latency=60, jitter=8, availability=99,
        outage_count=1, downtime_s=60, worst_outage_s=60, worst_outage_cause="isp",
        wifi_signal_avg=-78,  # weak → attribution should point at WiFi, not ISP
    ))
    titles = [f.title for f in v.findings]
    assert "Weak WiFi signal" in titles
    outage = next(f for f in v.findings if f.title.startswith("Internet unreachable"))
    assert "WiFi" in outage.detail


def test_high_latency_flagged_even_without_loss() -> None:
    # The user's real case: bandwidth fine, no loss, but p95 RTT ~130ms to the internet.
    v = conclude(WindowStats(
        loss=0.3, latency=130, jitter=8, bufferbloat=8, availability=100,
        wifi_signal_avg=-40, window_label="in the last 24h",
    ))
    latency = next((f for f in v.findings if f.title == "High latency to the internet"), None)
    assert latency is not None
    assert latency.severity == "warning"
    assert "latency" in v.headline.lower()


def test_dns_failures_flagged() -> None:
    v = conclude(WindowStats(loss=0, latency=20, availability=100, dns_fail=5, dns_total=50))
    assert any(f.title == "DNS failures" for f in v.findings)


def test_badly_peered_outlier_is_info_not_a_grade_killer() -> None:
    # The user's real case: 1.1.1.1 (Cloudflare) loses 7.5% on this ISP while every other
    # destination is ~1.3%. That's a peering issue to one host, not a broken connection — it must
    # be reported as info, NOT tank the grade, and NOT be phrased as systemic loss.
    v = conclude(WindowStats(
        loss=1.3, typical_loss=1.3, latency=20, jitter=5, bufferbloat=5, availability=100,
        worst_target=("1.1.1.1", 7.5), wifi_signal_avg=-45, window_label="in the last 24h",
    ))
    outlier = next(f for f in v.findings if "badly peered" in f.title)
    assert outlier.severity == "info"
    assert "1.1.1.1" in outlier.title
    # The old worst-path logic graded this F (Cloudflare 7.5%); grading the TYPICAL path (1.3%)
    # must not fail the connection and must not phrase it as systemic packet loss.
    assert v.score.grade not in ("D", "F")
    assert not any(f.title.startswith("Packet loss") for f in v.findings)


def test_broad_loss_is_still_an_error() -> None:
    # When the loss is NOT an outlier (every path is lossy), keep the hard packet-loss finding.
    v = conclude(WindowStats(
        loss=6, typical_loss=5.5, latency=60, availability=99,
        worst_target=("8.8.8.8", 6.0), wifi_signal_avg=-45,
    ))
    assert any(f.title.startswith("Packet loss") for f in v.findings)
    assert not any("badly peered" in f.title for f in v.findings)


def test_outage_breakdown_splits_laptop_isp_and_rf() -> None:
    v = conclude(WindowStats(
        loss=0, latency=30, availability=97,
        outage_count=4, downtime_s=300, worst_outage_s=200, worst_outage_cause="wifi/lan",
        outages_isp=1, outages_client_initiated=2, wifi_signal_avg=-45,
    ))
    outage = next(f for f in v.findings if f.title.startswith("Internet unreachable"))
    assert "1 ISP-side" in outage.detail
    assert "2 your laptop" in outage.detail
    assert "1 WiFi link" in outage.detail


def test_crowded_channel_reports_time_stuck() -> None:
    v = conclude(WindowStats(
        loss=0, latency=25, availability=100, wifi_signal_avg=-45,
        channel_advice=ChannelAdvice(
            current=149, aps_on_current=18, best_alternative=40, alternative_aps=0, crowded=True,
        ),
        hours_on_channel=8.0,
    ))
    ch = next(f for f in v.findings if "channel 149 is crowded" in f.title)
    assert "8 h" in ch.detail


def test_partial_coverage_is_flagged_so_results_arent_over_read() -> None:
    v = conclude(WindowStats(
        loss=0, latency=25, availability=100, coverage_pct=32.0, wifi_signal_avg=-45,
    ))
    note = next(f for f in v.findings if "Partial data" in f.title)
    assert note.severity == "info"
    assert "32%" in note.detail


def test_full_coverage_adds_no_note() -> None:
    v = conclude(WindowStats(
        loss=0, latency=25, availability=100, coverage_pct=99.0, wifi_signal_avg=-45,
    ))
    assert not any("Partial data" in f.title for f in v.findings)


def test_latency_anomaly_flags_deviation_from_own_normal() -> None:
    # Absolute latency alone wouldn't fire (< 100 ms), but 5 SD above this link's own history should.
    v = conclude(WindowStats(
        loss=0, latency=60, latency_anomaly_z=5.0, availability=100, wifi_signal_avg=-45,
    ))
    assert any('unusually high' in f.title for f in v.findings)


def test_stable_distant_link_is_not_an_anomaly() -> None:
    v = conclude(WindowStats(
        loss=0, latency=80, latency_anomaly_z=0.5, availability=100, wifi_signal_avg=-45,
    ))
    assert not any('unusually high' in f.title for f in v.findings)
