from datetime import date, timedelta
from pathlib import Path

from collector.domain.models import CollectorState
from collector.domain.trends import (
    STAR_HISTORY_DAYS,
    RisingRepository,
    record_stars,
    rising_repositories,
)
from collector.export.news import build_news_data
from collector.export.schema import SiteRisingRepository
from collector.export.site import build_site_data
from collector.store import load_state, save_state
from tests.test_classify import site_state
from tests.test_summarize import RANKING

TODAY = date(2026, 11, 20)


def days_ago(days: int) -> date:
    return TODAY - timedelta(days=days)


def test_one_value_per_day_keeps_the_latest() -> None:
    history = record_stars({}, {"acme/kit": 10}, TODAY)
    history = record_stars(history, {"acme/kit": 12}, TODAY)
    assert history == {"acme/kit": {TODAY: 12}}


def test_old_snapshots_are_dropped() -> None:
    history = {"acme/kit": {days_ago(STAR_HISTORY_DAYS + 1): 1, days_ago(3): 5}}
    updated = record_stars(history, {"acme/kit": 6}, TODAY)
    assert updated == {"acme/kit": {days_ago(3): 5, TODAY: 6}}


def test_repositories_that_disappear_lose_their_history_over_time() -> None:
    history = {"gone/repo": {days_ago(STAR_HISTORY_DAYS + 1): 9}}
    assert record_stars(history, {}, TODAY) == {}


def test_rising_needs_a_full_window_and_sorts_by_gain() -> None:
    history = {
        "a/fast": {days_ago(7): 100, TODAY: 400},
        "b/slow": {days_ago(8): 50, days_ago(7): 60, TODAY: 70},
        "c/new": {days_ago(2): 1, TODAY: 900},
        "d/flat": {days_ago(7): 30, TODAY: 30},
    }
    rising = rising_repositories(history, window_days=7, limit=10)
    assert rising == [
        RisingRepository(key="a/fast", gained=300, stars=400),
        RisingRepository(key="b/slow", gained=10, stars=70),
    ]


def test_rising_measures_from_the_latest_snapshot_not_the_clock() -> None:
    history = {"a/fast": {days_ago(17): 10, days_ago(10): 40}}
    assert rising_repositories(history, window_days=7, limit=10) == [
        RisingRepository(key="a/fast", gained=30, stars=40)
    ]


def test_rising_is_capped() -> None:
    history = {f"r/{i}": {days_ago(7): 0, TODAY: i + 1} for i in range(20)}
    assert len(rising_repositories(history, window_days=7, limit=5)) == 5


def test_empty_history_has_nothing_rising() -> None:
    assert rising_repositories({}, window_days=7, limit=5) == []


def test_star_history_survives_a_save_and_load(tmp_path: Path) -> None:
    state = CollectorState(star_history={"acme/kit": {days_ago(7): 1, TODAY: 5}})
    save_state(state, tmp_path)
    assert load_state(tmp_path).star_history == state.star_history


def test_news_lists_only_repositories_on_the_site() -> None:
    state = site_state()
    state.star_history = {
        "acme/kit": {days_ago(7): 1, TODAY: 6},
        "other/repo": {days_ago(7): 1, TODAY: 900},
    }
    site = build_site_data(state, RANKING)

    news = build_news_data(state, site)

    assert news.rising_repositories == (
        SiteRisingRepository(full_name="acme/kit", stars_gained=5, stars=6, window_days=7),
    )
    assert "risingRepositories" in news.model_dump(by_alias=True)
