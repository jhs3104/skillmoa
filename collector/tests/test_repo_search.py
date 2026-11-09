from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from collector.domain.models import Repository
from collector.sources.github import RateLimitExceededError, RepositorySearchPage
from collector.sources.repo_search import discover_by_stars

QUERY = "skill in:name,description,topics"


def repo(name: str, stars: int) -> Repository:
    return Repository(
        github_id=abs(hash(name)) % 10**9,
        owner="acme",
        name=name,
        stars=stars,
        pushed_at=datetime(2026, 11, 1, tzinfo=UTC),
        license="MIT",
        default_branch="main",
    )


def fake_search(
    stars: list[int],
) -> tuple[Callable[[str, int], RepositorySearchPage], list[tuple[str, int]]]:
    """stars 내림차순 목록을 GitHub처럼 창(stars:lo..hi)과 1,000건 제한으로 돌려준다."""
    queries: list[tuple[str, int]] = []

    def search(query: str, page: int) -> RepositorySearchPage:
        queries.append((query, page))
        window = query.rsplit("stars:", 1)[1]
        if window.startswith(">="):
            low, high = int(window[2:]), 10**9
        else:
            low_text, high_text = window.split("..")
            low, high = int(low_text), int(high_text)
        matching = [(index, count) for index, count in enumerate(stars) if low <= count <= high]
        page_items = matching[(page - 1) * 100 : page * 100] if page <= 10 else []
        return RepositorySearchPage(
            total_count=len(matching),
            repositories=[repo(f"r{index}", count) for index, count in page_items],
        )

    return search, queries


def test_reads_every_repository_above_the_floor_across_windows() -> None:
    stars = [5000 - index for index in range(2500)]
    search, queries = fake_search(stars)

    scan = discover_by_stars(search, QUERY, min_stars=10)

    assert len(scan.repositories) == 2500
    assert scan.complete
    assert all(page <= 10 for _, page in queries)
    assert queries[0][0] == f"{QUERY} stars:>=10"
    assert queries[10][0] == f"{QUERY} stars:10..4001"


def test_ties_at_a_window_edge_do_not_loop_forever() -> None:
    stars = [100] * 1200 + [50] * 10
    search, queries = fake_search(stars)

    scan = discover_by_stars(search, QUERY, min_stars=10)

    assert scan.complete
    assert {repository.stars for repository in scan.repositories.values()} == {100, 50}
    assert len(queries) < 40


def test_stops_when_time_runs_out_but_keeps_what_it_read() -> None:
    search, _ = fake_search([5000 - index for index in range(2500)])

    scan = discover_by_stars(search, QUERY, min_stars=10, should_stop=lambda: True)

    assert len(scan.repositories) == 1000
    assert not scan.complete


def test_errors_stop_the_query_but_keep_results() -> None:
    def search(query: str, page: int) -> RepositorySearchPage:
        if page == 2:
            raise RateLimitExceededError("wait")
        return RepositorySearchPage(1500, [repo(f"p{page}-{index}", 900) for index in range(100)])

    scan = discover_by_stars(search, QUERY, min_stars=10)
    assert len(scan.repositories) == 100
    assert not scan.complete


def test_http_errors_stop_the_query_but_keep_results() -> None:
    request = httpx.Request("GET", "https://api.github.com/search/repositories")

    def search(query: str, page: int) -> RepositorySearchPage:
        if page == 2:
            raise httpx.HTTPStatusError("422", request=request, response=httpx.Response(422))
        return RepositorySearchPage(1500, [repo(f"p{page}-{index}", 900) for index in range(100)])

    assert len(discover_by_stars(search, QUERY, min_stars=10).repositories) == 100
