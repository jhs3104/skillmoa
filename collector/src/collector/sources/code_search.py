"""코드 검색으로 SKILL.md를 전수 조회한다.

코드 검색은 쿼리당 1,000건까지만 돌려주고 날짜 한정자와 스타 정렬을 지원하지 않는다.
그래서 파일 크기 범위를 나눠가며 각 범위가 1,000건 이하가 되도록 조회한다.
"""

import math
from collections.abc import Callable

from collector.sources.github import RESULTS_PER_PAGE, SEARCH_RESULT_CAP, CodeSearchPage

Search = Callable[[str, int], CodeSearchPage]


def size_query(low: int, high: int) -> str:
    return f"filename:SKILL.md size:{low}..{high}"


def discover_by_size(search: Search, max_size: int) -> set[str]:
    repositories: set[str] = set()
    pending = [(0, max_size)]
    while pending:
        low, high = pending.pop()
        query = size_query(low, high)
        first = search(query, 1)
        if first.total_count > SEARCH_RESULT_CAP and low < high:
            middle = (low + high) // 2
            pending += [(low, middle), (middle + 1, high)]
            continue
        repositories.update(first.repositories)
        # 1,000건 뒤의 페이지를 요청하면 GitHub가 422로 거부한다.
        last_page = math.ceil(min(first.total_count, SEARCH_RESULT_CAP) / RESULTS_PER_PAGE)
        for page in range(2, last_page + 1):
            repositories.update(search(query, page).repositories)
    return repositories
