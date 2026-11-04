"""도구 업데이트 소스 (ADR-0022). Claude Code·Codex는 GitHub Releases, Cursor는 공식 RSS다."""

import logging
import re
import xml.etree.ElementTree as ElementTree
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from collector.domain.models import Tool
from collector.domain.tool_news import ToolRelease
from collector.sources.github import GitHubClient, RateLimitExceededError

logger = logging.getLogger(__name__)

GITHUB_REPOSITORIES = {Tool.CLAUDE_CODE: "anthropics/claude-code", Tool.CODEX: "openai/codex"}
CURSOR_FEED_URL = "https://cursor.com/changelog/rss.xml"
_CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
# Codex 태그는 "rust-v0.166.0", Claude Code 태그는 "v2.1.318"이다.
_TAG_PREFIX = re.compile(r"^(?:rust-)?v")
_BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "br", "pre", "tr"}


def parse_github_releases(body: list[dict[str, Any]], tool: Tool) -> list[ToolRelease]:
    """정식 릴리스만 남긴다. 알파와 초안은 본문이 거의 비어 있다."""
    releases: list[ToolRelease] = []
    for item in body:
        if item.get("draft") or item.get("prerelease") or not item.get("published_at"):
            continue
        published = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00")).date()
        releases.append(
            ToolRelease(
                tool=tool,
                version=_TAG_PREFIX.sub("", item["tag_name"]),
                published=published,
                url=item["html_url"],
                notes=item.get("body") or "",
            )
        )
    return releases


def parse_cursor_feed(feed: str) -> list[ToolRelease]:
    """RSS 글마다 하나의 릴리스로 본다. 본문 HTML은 글자만 남긴다."""
    channel = ElementTree.fromstring(feed).find("channel")
    if channel is None:
        return []
    releases: list[ToolRelease] = []
    for item in channel.findall("item"):
        published = _rss_date(item.findtext("pubDate"))
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if published is None or not title or not link:
            continue
        html = item.findtext(_CONTENT) or item.findtext("description") or ""
        releases.append(
            ToolRelease(
                tool=Tool.CURSOR, version=title, published=published, url=link, notes=_text(html)
            )
        )
    return releases


def fetch_tool_releases(github: GitHubClient, http: httpx.Client) -> list[ToolRelease]:
    """소스 하나가 실패해도 나머지는 가져온다. 실패는 다음 실행에서 다시 시도한다."""
    releases: list[ToolRelease] = []
    for tool, repository in GITHUB_REPOSITORIES.items():
        try:
            releases += parse_github_releases(github.list_releases(repository), tool)
        except (httpx.HTTPError, RateLimitExceededError, KeyError, ValueError) as error:
            logger.warning("릴리스를 가져오지 못했습니다 %s: %s", repository, error)
    try:
        releases += parse_cursor_feed(_get_feed(http))
    except (httpx.HTTPError, ElementTree.ParseError) as error:
        logger.warning("Cursor 변경 기록을 가져오지 못했습니다: %s", error)
    return releases


@retry(
    retry=retry_if_exception_type(httpx.TransportError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, max=30),
    reraise=True,
)
def _get_feed(http: httpx.Client) -> str:
    response = http.get(CURSOR_FEED_URL)
    response.raise_for_status()
    return response.text


def _rss_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError):
        return None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    lines = (" ".join(line.split()) for line in "".join(extractor.parts).splitlines())
    return "\n".join(line for line in lines if line)
