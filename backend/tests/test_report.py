from netpulse.analysis.report import (
    ReportContext,
    ReportRow,
    ReportSection,
    build_report_html,
)


def test_report_is_self_contained_and_escaped() -> None:
    ctx = ReportContext(
        generated_at="2026-08-14 15:00",
        network_label="Home <5G>",
        window_label="the last 24 hours",
        grade="B",
        headline="Mostly healthy",
        sections=[ReportSection("Findings", [ReportRow("INFO", "All good & fine")])],
        methodology="method",
    )
    out = build_report_html(ctx)
    assert "<!doctype html>" in out
    assert "http://" not in out and "https://" not in out  # no external assets
    assert "Home &lt;5G&gt;" in out  # HTML-escaped
    assert "All good &amp; fine" in out
    assert "Grade B" in out
