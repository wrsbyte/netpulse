from netpulse.analysis.experience import ExperienceInputs, assess


def _by(vs, name):
    return next(v for v in vs if v.activity == name)


def test_clean_connection_rates_everything_good() -> None:
    vs = assess(ExperienceInputs(
        rtt_ms=18, loss_pct=0.3, jitter_ms=4, bufferbloat_ms=8, download_mbps=196, dns_ms=20,
    ))
    assert all(v.rating == "good" for v in vs)


def test_bufferbloat_breaks_calls_but_not_browsing() -> None:
    # High latency-under-load ruins calls even when idle latency and bandwidth are fine.
    vs = assess(ExperienceInputs(
        rtt_ms=18, loss_pct=0.3, jitter_ms=4, bufferbloat_ms=180, download_mbps=196, dns_ms=20,
    ))
    assert _by(vs, "Video calls").rating == "poor"
    assert _by(vs, "Browsing").rating == "good"


def test_worst_activity_is_first() -> None:
    vs = assess(ExperienceInputs(
        rtt_ms=18, loss_pct=8, jitter_ms=40, bufferbloat_ms=200, download_mbps=196, dns_ms=20,
    ))
    assert vs[0].rating == "poor"
    assert _RATING_ok(vs)


def _RATING_ok(vs) -> bool:
    ranks = {"poor": 0, "fair": 1, "good": 2, "unknown": 3}
    return all(ranks[vs[i].rating] <= ranks[vs[i + 1].rating] for i in range(len(vs) - 1))


def test_missing_data_is_unknown_not_poor() -> None:
    vs = assess(ExperienceInputs())
    assert {v.rating for v in vs} == {"unknown"}


def test_metrics_carry_the_technical_numbers() -> None:
    vs = assess(ExperienceInputs(rtt_ms=18, loss_pct=0.3, jitter_ms=4, dns_ms=20))
    browsing = _by(vs, "Browsing")
    labels = {m.label: m.value for m in browsing.metrics}
    assert labels["Latency"] == 18
    assert labels["DNS lookup"] == 20


def test_calls_use_live_media_path_when_active() -> None:
    # A live call with clean UDP path -> good, and the summary names the app.
    vs = assess(ExperienceInputs(
        bufferbloat_ms=200, jitter_ms=40, loss_pct=8,  # proxies say poor...
        media_jitter_ms=5, media_loss_pct=0.2, media_app="Meet",  # ...but the real call is clean
    ))
    calls = next(v for v in vs if v.activity == "Video calls")
    assert calls.rating == "good"
    assert "Meet" in calls.summary
    assert any("live" in m.label for m in calls.metrics)
