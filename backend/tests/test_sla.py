from netpulse.analysis.sla import Measured, SlaTargets, assess


def test_capacity_meets_at_90pct_breaches_below() -> None:
    r = assess(
        SlaTargets(download_mbps=200, upload_mbps=200, uptime_pct=99.5),
        Measured(download_mbps=185, upload_mbps=150, uptime_pct=99.9),
    )
    by = {line.metric: line for line in r.lines}
    assert by["Download"].meets is True  # 185/200 = 92.5% >= 90%
    assert by["Upload"].meets is False  # 150/200 = 75% < 90%
    assert by["Uptime"].meets is True  # 99.9 >= 99.5
    assert r.breaches == 1


def test_unmeasured_metric_is_pending_not_a_breach() -> None:
    r = assess(SlaTargets(download_mbps=100), Measured(download_mbps=None))
    assert r.lines[0].meets is None
    assert r.breaches == 0


def test_no_contract_is_unconfigured() -> None:
    assert assess(SlaTargets(), Measured(download_mbps=100)).configured is False


def test_latency_ceiling_is_lower_is_better() -> None:
    r = assess(SlaTargets(latency_ms=50), Measured(latency_ms=40))
    assert r.lines[0].meets is True
    r2 = assess(SlaTargets(latency_ms=50), Measured(latency_ms=80))
    assert r2.lines[0].meets is False
