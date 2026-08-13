from netpulse.analysis.verdict import WindowStats, conclude
from netpulse.api.routers.data import to_verdict_out


def test_verdict_serializes_slotted_dataclasses() -> None:
    # Verdict's score/findings are frozen+slots dataclasses (no __dict__); the converter must
    # use asdict, not vars — this reproduces the 500 the endpoint raised.
    verdict = conclude(WindowStats(
        loss=15, latency=140, jitter=20, availability=95,
        outage_count=2, downtime_s=300, worst_outage_s=200, worst_outage_cause="isp",
        worst_target=("1.1.1.1", 15.0), window_label="in the last 24h",
    ))
    out = to_verdict_out(verdict)
    assert out.headline == verdict.headline
    assert out.score.grade == verdict.score.grade
    assert len(out.findings) == len(verdict.findings)
    assert out.findings[0].severity == "error"
