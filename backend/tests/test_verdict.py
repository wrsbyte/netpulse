from netpulse.analysis.verdict import WindowStats, conclude


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
