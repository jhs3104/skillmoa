"""저장소 검색으로 스타가 많은 스킬 저장소부터 찾는다.

검색은 쿼리당 1,000건까지만 돌려준다. 스타 내림차순으로 1,000건을 읽고, 마지막으로 본 스타 수를
다음 창의 상한으로 삼아 내려간다. 사이트는 스타순 상위만 싣으므로 하한(min_stars)에서 멈춘다.
"""

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from collector.domain.identity import repository_key
from collector.domain.models import Repository
from collector.sources.github import (
    RESULTS_PER_PAGE,
    SEARCH_RESULT_CAP,
    GitHubUnavailableError,
    RateLimitExceededError,
    RepositorySearchPage,
)

logger = logging.getLogger(__name__)

Search = Callable[[str, int], RepositorySearchPage]
LAST_PAGE = SEARCH_RESULT_CAP // RESULTS_PER_PAGE


@dataclass
class StarScan:
    repositories: dict[str, Repository] = field(default_factory=dict)
    complete: bool = False


def star_window(query: str, min_stars: int, upper: int | None) -> str:
    if upper is None:
        return f"{query} stars:>={min_stars}"
    return f"{query} stars:{min_stars}..{upper}"


def discover_by_stars(
    search: Search,
    query: str,
    min_stars: int,
    should_stop: Callable[[], bool] = lambda: False,
) -> StarScan:
    """창 하나(최대 10페이지)를 다 읽은 뒤에만 멈춘다. 매 실행이 적어도 한 창은 읽는다."""
    scan = StarScan()
    upper: int | None = None
    try:
        while True:
            window = star_window(query, min_stars, upper)
            total, lowest = _read_window(search, window, scan)
            if total <= SEARCH_RESULT_CAP or lowest is None:
                scan.complete = True
                return scan
            # 같은 스타 수가 창 경계에 걸치면 상한이 줄지 않는다. 그때만 한 칸 내린다.
            next_upper = lowest if lowest != upper else lowest - 1
            if next_upper < min_stars:
                scan.complete = True
                return scan
            if should_stop():
                logger.warning("저장소 검색 시간 예산 소진: %s", window)
                return scan
            upper = next_upper
    except RateLimitExceededError as error:
        logger.warning("저장소 검색을 레이트 리밋으로 멈춥니다: %s", error)
    except (httpx.HTTPError, GitHubUnavailableError) as error:
        logger.warning("저장소 검색 실패 %s: %s", query, error)
    return scan


def _read_window(search: Search, window: str, scan: StarScan) -> tuple[int, int | None]:
    total = 0
    lowest: int | None = None
    for page in range(1, LAST_PAGE + 1):
        result = search(window, page)
        total = result.total_count
        for repository in result.repositories:
            scan.repositories[repository_key(repository.full_name)] = repository
            lowest = repository.stars if lowest is None else min(lowest, repository.stars)
        last_page = math.ceil(min(total, SEARCH_RESULT_CAP) / RESULTS_PER_PAGE)
        if len(result.repositories) < RESULTS_PER_PAGE or page >= last_page:
            break
    return total, lowest
