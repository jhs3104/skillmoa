"""코드 검색으로 SKILL.md를 전수 조회한다.

코드 검색은 쿼리당 1,000건까지만 돌려주고 날짜 한정자와 스타 정렬을 지원하지 않는다.
그래서 파일 크기 범위를 나눠가며 각 범위가 1,000건 이하가 되도록 조회한다.

전체 조회는 두 시간 넘게 걸린다. 한 범위가 실패해도 그때까지 찾은 저장소는 버리지 않는다.
"""

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from collector.sources.github import (
    RESULTS_PER_PAGE,
    SEARCH_RESULT_CAP,
    CodeSearchPage,
    GitHubUnavailableError,
    RateLimitExceededError,
)

logger = logging.getLogger(__name__)

Search = Callable[[str, int], CodeSearchPage]


@dataclass
class SizeScan:
    repositories: set[str] = field(default_factory=set)
    failed_ranges: int = 0
    stopped_by_rate_limit: bool = False

    @property
    def complete(self) -> bool:
        return self.failed_ranges == 0 and not self.stopped_by_rate_limit


def size_query(low: int, high: int) -> str:
    return f"filename:SKILL.md size:{low}..{high}"


def discover_by_size(search: Search, max_size: int) -> SizeScan:
    scan = SizeScan()
    pending = [(0, max_size)]
    while pending:
        low, high = pending.pop()
        query = size_query(low, high)
        try:
            first = search(query, 1)
            if first.total_count > SEARCH_RESULT_CAP and low < high:
                middle = (low + high) // 2
                pending += [(low, middle), (middle + 1, high)]
                continue
            scan.repositories.update(first.repositories)
            # 1,000건 뒤의 페이지를 요청하면 GitHub가 422로 거부한다.
            last_page = math.ceil(min(first.total_count, SEARCH_RESULT_CAP) / RESULTS_PER_PAGE)
            for page in range(2, last_page + 1):
                scan.repositories.update(search(query, page).repositories)
        except RateLimitExceededError as error:
            logger.warning("코드 검색을 레이트 리밋으로 멈춥니다. 찾은 곳까지 씁니다: %s", error)
            scan.stopped_by_rate_limit = True
            break
        except (httpx.HTTPError, GitHubUnavailableError) as error:
            logger.warning("코드 검색 범위를 건너뜁니다 %s: %s", query, error)
            scan.failed_ranges += 1
    return scan
