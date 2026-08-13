import time
from pathlib import Path

from netpulse.api import queries
from netpulse.api.queries import RawQuery
from netpulse.api.routers.raw import _TABLES
from netpulse.db.models import PingRaw
from netpulse.db.session import get_session, init_engine

MODEL, SPECS = _TABLES["ping"]


def _seed(tmp_path: Path) -> float:
    init_engine(tmp_path / "raw.db")
    now = time.time()
    with get_session() as s:
        s.add_all([
            PingRaw(ts=now - 1, target="1.1.1.1", loss_pct=20.0, rtt_avg=100.0),
            PingRaw(ts=now - 2, target="1.1.1.1", loss_pct=0.0, rtt_avg=90.0),
            PingRaw(ts=now - 3, target="8.8.8.8", loss_pct=0.0, rtt_avg=20.0),
        ])
        s.commit()
    return now


def test_aggregates_run_over_the_filtered_set(tmp_path: Path) -> None:
    _seed(tmp_path)
    with get_session() as s:
        page = queries.raw_page(s, MODEL, SPECS, RawQuery(window=3600, network_id=None), 100, 0)
    assert page.total == 3
    rtt = next(a for a in page.agg if a.column == "rtt_avg")
    assert rtt.count == 3
    assert rtt.min == 20.0
    assert rtt.max == 100.0


def test_filter_narrows_rows_and_aggregates(tmp_path: Path) -> None:
    _seed(tmp_path)
    with get_session() as s:
        rq = RawQuery(window=3600, network_id=None, filters={"target": "1.1.1.1"})
        page = queries.raw_page(s, MODEL, SPECS, rq, 100, 0)
    assert page.total == 2
    rtt = next(a for a in page.agg if a.column == "rtt_avg")
    assert rtt.max == 100.0 and rtt.min == 90.0  # 8.8.8.8's 20ms excluded by the filter


def test_sort_ascending_by_a_numeric_column(tmp_path: Path) -> None:
    _seed(tmp_path)
    with get_session() as s:
        rq = RawQuery(window=3600, network_id=None, sort="rtt_avg", descending=False)
        page = queries.raw_page(s, MODEL, SPECS, rq, 100, 0)
    assert [r["rtt_avg"] for r in page.rows] == [20.0, 90.0, 100.0]


def test_enum_column_exposes_distinct_values_for_filters(tmp_path: Path) -> None:
    _seed(tmp_path)
    with get_session() as s:
        page = queries.raw_page(s, MODEL, SPECS, RawQuery(window=3600, network_id=None), 100, 0)
    target_col = next(c for c in page.columns if c.name == "target")
    assert target_col.values == ["1.1.1.1", "8.8.8.8"]
    assert target_col.unit is None
    rtt_col = next(c for c in page.columns if c.name == "rtt_avg")
    assert rtt_col.unit == "ms"


def test_facet_values_ignore_the_active_filter(tmp_path: Path) -> None:
    # With target filtered to one value, the dropdown must still list all values so the
    # user can switch — facets are computed over the window, not the filtered rows.
    _seed(tmp_path)
    with get_session() as s:
        rq = RawQuery(window=3600, network_id=None, filters={"target": "1.1.1.1"})
        page = queries.raw_page(s, MODEL, SPECS, rq, 100, 0)
    assert page.total == 2  # rows are filtered
    target_col = next(c for c in page.columns if c.name == "target")
    assert target_col.values == ["1.1.1.1", "8.8.8.8"]  # but facets are not
