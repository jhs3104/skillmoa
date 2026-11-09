"""GitHub REST 클라이언트. 레이트 리밋과 재시도를 이 모듈에서 전부 처리한다."""

import logging
import math
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import quote

import httpx
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from collector.domain.models import Repository
from collector.domain.tree import TreeEntry

logger = logging.getLogger(__name__)

API_URL = "https://api.github.com"
RAW_URL = "https://raw.githubusercontent.com"
API_VERSION = "2022-11-28"
MAX_ATTEMPTS = 6
RESULTS_PER_PAGE = 100
SEARCH_RESULT_CAP = 1000
SECONDARY_LIMIT_WAIT_SECONDS = 60.0
REQUEST_TIMEOUT_SECONDS = 30.0


class Resource(StrEnum):
    """GitHub가 호출 한도를 따로 세는 단위."""

    CORE = "core"
    SEARCH = "search"
    CODE_SEARCH = "code_search"


class GitHubUnavailableError(Exception):
    """재시도할 수 있는 일시적 실패."""


class RateLimitExceededError(Exception):
    """허용한 대기 시간 안에 한도가 풀리지 않는다. 호출 측은 상태를 저장하고 멈춘다."""


@dataclass(frozen=True)
class RepositoryTree:
    entries: list[TreeEntry]
    truncated: bool


@dataclass(frozen=True)
class CodeSearchPage:
    total_count: int
    repositories: list[str]


class GitHubClient:
    def __init__(
        self,
        token: str | None,
        max_wait_seconds: float,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            headers=headers,
            transport=transport,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        self.authenticated = bool(token)
        self._max_wait = max_wait_seconds
        self._wait_deadline = math.inf
        self._sleep = sleep
        self._clock = clock
        search_interval = 60 / (30 if token else 10)
        self._intervals = {
            Resource.CORE: 0.0,
            Resource.SEARCH: search_interval,
            Resource.CODE_SEARCH: 6.0,
        }
        self._not_before = dict.fromkeys(Resource, 0.0)

    def close(self) -> None:
        self._http.close()

    def stop_waiting_after(self, deadline: float) -> None:
        """한도가 이 시각(clock 기준) 뒤에 풀리면 기다리지 않고 RateLimitExceededError를 낸다."""
        self._wait_deadline = deadline

    def get_repository(self, full_name: str) -> Repository | None:
        response = self._get(Resource.CORE, f"{API_URL}/repos/{full_name}")
        if response.status_code in (403, 404, 451):
            return None
        response.raise_for_status()
        return parse_repository(response.json())

    def get_tree(self, repository: Repository) -> RepositoryTree | None:
        """빈 저장소(409)나 사라진 브랜치(404)는 None을 돌려준다."""
        url = f"{API_URL}/repos/{repository.full_name}/git/trees/{repository.default_branch}"
        response = self._get(Resource.CORE, url, {"recursive": "1"})
        if response.status_code in (404, 409):
            return None
        response.raise_for_status()
        body = response.json()
        entries = [
            TreeEntry(path=item["path"], sha=item["sha"], size=item.get("size", 0))
            for item in body["tree"]
            if item["type"] == "blob"
        ]
        return RepositoryTree(entries=entries, truncated=body.get("truncated", False))

    def search_repositories(self, query: str, pages: int) -> Iterator[Repository]:
        params = {"q": query, "sort": "stars", "order": "desc", "per_page": str(RESULTS_PER_PAGE)}
        for page in range(1, pages + 1):
            response = self._get(
                Resource.SEARCH,
                f"{API_URL}/search/repositories",
                params | {"page": str(page)},
            )
            response.raise_for_status()
            items = response.json()["items"]
            yield from (parse_repository(item) for item in items)
            if len(items) < RESULTS_PER_PAGE or page * RESULTS_PER_PAGE >= SEARCH_RESULT_CAP:
                return

    def search_code(self, query: str, page: int) -> CodeSearchPage:
        response = self._get(
            Resource.CODE_SEARCH,
            f"{API_URL}/search/code",
            {"q": query, "per_page": str(RESULTS_PER_PAGE), "page": str(page)},
        )
        response.raise_for_status()
        body = response.json()
        repositories = [item["repository"]["full_name"] for item in body["items"]]
        return CodeSearchPage(total_count=body["total_count"], repositories=repositories)

    def list_releases(self, full_name: str, per_page: int = 40) -> list[dict[str, Any]]:
        """최근 릴리스를 최신순으로 돌려준다. 해석은 sources.tool_releases가 한다."""
        response = self._get(
            Resource.CORE, f"{API_URL}/repos/{full_name}/releases", {"per_page": str(per_page)}
        )
        response.raise_for_status()
        releases: list[dict[str, Any]] = response.json()
        return releases

    def fetch_raw(self, full_name: str, ref: str, path: str) -> bytes | None:
        """raw 호스트는 API 한도를 쓰지 않는다. 호출 횟수를 신경 쓰지 않아도 된다."""
        url = f"{RAW_URL}/{full_name}/{quote(ref)}/{quote(path)}"
        response = self._send(lambda: self._http.get(url))
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content

    def _get(
        self, resource: Resource, url: str, params: dict[str, str] | None = None
    ) -> httpx.Response:
        def attempt() -> httpx.Response:
            self._await_slot(resource)
            response = self._http.get(url, params=params)
            self._observe(resource, response)
            return response

        return self._send(attempt)

    def _send(self, attempt: Callable[[], httpx.Response]) -> httpx.Response:
        def checked() -> httpx.Response:
            response = attempt()
            if response.status_code >= 500 or response.status_code == 429:
                raise GitHubUnavailableError(f"{response.status_code} {response.url}")
            return response

        retrying = Retrying(
            stop=stop_after_attempt(MAX_ATTEMPTS),
            wait=wait_exponential(multiplier=1, max=60),
            retry=retry_if_exception_type((GitHubUnavailableError, httpx.TransportError)),
            sleep=self._sleep,
            before_sleep=_log_retry,
            reraise=True,
        )
        return retrying(checked)

    def _await_slot(self, resource: Resource) -> None:
        now = self._clock()
        wait = self._not_before[resource] - now
        if wait > self._max_wait or now + wait > self._wait_deadline:
            raise RateLimitExceededError(f"{resource}: {wait:.0f}초 대기 필요")
        if wait > 0:
            logger.info("%s 한도 대기 %.1f초", resource, wait)
            self._sleep(wait)
        self._not_before[resource] = self._clock() + self._intervals[resource]

    def _observe(self, resource: Resource, response: httpx.Response) -> None:
        now = self._clock()
        headers = response.headers
        if headers.get("x-ratelimit-remaining") == "0" and "x-ratelimit-reset" in headers:
            reset_at = float(headers["x-ratelimit-reset"]) + 1
            self._not_before[resource] = max(self._not_before[resource], reset_at)

        if _is_rate_limited(response):
            if "retry-after" in headers:
                until = now + float(headers["retry-after"])
                self._not_before[resource] = max(self._not_before[resource], until)
            elif self._not_before[resource] <= now:
                self._not_before[resource] = now + SECONDARY_LIMIT_WAIT_SECONDS
            raise GitHubUnavailableError(f"rate limited: {response.url}")


def parse_repository(item: dict[str, Any]) -> Repository:
    license_info = item.get("license") or {}
    spdx_id = license_info.get("spdx_id")
    return Repository(
        github_id=item["id"],
        owner=item["owner"]["login"],
        name=item["name"],
        stars=item["stargazers_count"],
        pushed_at=item["pushed_at"],
        license=None if spdx_id in (None, "NOASSERTION") else spdx_id,
        default_branch=item["default_branch"],
        description=item.get("description"),
        is_fork=item.get("fork", False),
        is_archived=item.get("archived", False),
    )


def _is_rate_limited(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    headers = response.headers
    return (
        "retry-after" in headers
        or headers.get("x-ratelimit-remaining") == "0"
        or "rate limit" in response.text.lower()
    )


def _log_retry(state: RetryCallState) -> None:
    logger.warning("GitHub 재시도 %d회차: %s", state.attempt_number, state.outcome.exception())
