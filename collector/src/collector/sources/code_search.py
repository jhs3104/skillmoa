"""코드 검색으로 SKILL.md를 전수 조회한다.

코드 검색은 쿼리당 1,000건까지만 돌려주고 날짜 한정자와 스타 정렬을 지원하지 않는다.
그래서 파일 크기 범위를 나눠가며 각 범위가 1,000건 이하가 되도록 조회한다.

전체 조회는 한 실행의 제한 시간보다 오래 걸린다.
그래서 남은 범위를 돌려주고 다음 실행이 이어서 읽는다.
한 범위가 실패하면 그 범위만 건너뛴다.
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
SizeRange = tuple[int, int]


@dataclass
class SizeScan:
    repositories: set[str] = field(default_factory=set)
    # 아직 읽지 않은 크기 범위. 상태에 저장해 다음 실행이 이어서 읽는다.
    remaining: list[SizeRange] = field(default_factory=list)
    failed_ranges: int = 0
    stopped_by_rate_limit: bool = False

    @property
    def finished(self) -> bool:
        return not self.remaining


def size_query(low: int, high: int) -> str:
    return f"filename:SKILL.md size:{low}..{high}"


def discover_by_size(
    search: Search, ranges: list[SizeRange], should_stop: Callable[[], bool] = lambda: False
) -> SizeScan:
    """ranges를 읽는다. 매 실행이 앞으로 나아가도록 첫 범위는 시간과 상관없이 읽는다."""
    scan = SizeScan()
    pending = list(ranges)
    read_any = False
    while pending:
        if read_any and should_stop():
            break
        read_any = True
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
            pending.append((low, high))
            break
        except (httpx.HTTPError, GitHubUnavailableError) as error:
            logger.warning("코드 검색 범위를 건너뜁니다 %s: %s", query, error)
            scan.failed_ranges += 1
    scan.remaining = pending
    return scan
