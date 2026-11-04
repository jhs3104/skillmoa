from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from collector.config import Settings
from collector.domain.models import CollectorState, ToolUpdateRecord
from collector.domain.tool_news import (
    Tool,
    ToolRelease,
    group_releases,
    needs_tool_summary,
    prune_tool_updates,
)
from collector.export.news import build_news_data, build_tool_updates_data
from collector.export.schema import SiteData, SiteToolUpdate
from collector.pipeline.collect import CollectContext
from collector.pipeline.run import Paths, run_tool_news
from collector.pipeline.tool_news import update_tool_news
from collector.sources.tool_releases import parse_cursor_feed, parse_github_releases
from collector.store import save_state
from collector.summarize.base import SummaryRejectedError, ToolNewsRequest, ToolNewsResult
from collector.summarize.tool_news import ClaudeToolNewsWriter
from collector.summarize.tool_news_prompts import TOOL_NEWS_PROMPTS
from tests.conftest import make_client
from tests.test_summarize import anthropic_client

TODAY = date(2026, 11, 4)


def release(tool: Tool = Tool.CLAUDE_CODE, version: str = "2.1.318", **fields: Any) -> ToolRelease:
    values: dict[str, Any] = {
        "tool": tool,
        "version": version,
        "published": TODAY,
        "url": f"https://example.com/{version}",
        "notes": f"- Added things in {version}",
    }
    return ToolRelease(**(values | fields))


def record(**fields: Any) -> ToolUpdateRecord:
    values: dict[str, Any] = {
        "tool": Tool.CLAUDE_CODE,
        "day": TODAY,
        "versions": ("2.1.318",),
        "url": "https://example.com/2.1.318",
        "source_hash": "a" * 64,
        "highlights": ("세션을 이어 할 때 대화를 잃던 문제를 고쳤습니다.",),
        "prompt_version": "n1",
        "model": "m",
    }
    return ToolUpdateRecord(**(values | fields))


class TestParsing:
    def test_github_releases_skip_drafts_and_prereleases(self) -> None:
        body = [
            {
                "tag_name": "rust-v0.168.0-alpha.1",
                "prerelease": True,
                "draft": False,
                "published_at": "2026-11-04T02:54:53Z",
                "html_url": "u1",
                "body": "x",
            },
            {
                "tag_name": "rust-v0.166.0",
                "prerelease": False,
                "draft": False,
                "published_at": "2026-10-29T10:00:00Z",
                "html_url": "u2",
                "body": "## New",
            },
            {
                "tag_name": "v9",
                "prerelease": False,
                "draft": True,
                "published_at": None,
                "html_url": "u3",
                "body": "draft",
            },
        ]
        releases = parse_github_releases(body, Tool.CODEX)
        assert releases == [ToolRelease(Tool.CODEX, "0.166.0", date(2026, 10, 29), "u2", "## New")]

    def test_claude_code_tags_lose_the_v(self) -> None:
        body = [
            {
                "tag_name": "v2.1.318",
                "prerelease": False,
                "draft": False,
                "published_at": "2026-11-04T00:01:03Z",
                "html_url": "u",
                "body": "- a",
            }
        ]
        assert parse_github_releases(body, Tool.CLAUDE_CODE)[0].version == "2.1.318"

    def test_cursor_feed_items_become_releases(self) -> None:
        feed = """<?xml version="1.0"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Agent SDK</title><link>https://cursor.com/changelog/agent-sdk</link>
<pubDate>Tue, 20 Oct 2026 00:00:00 GMT</pubDate><description>Short.</description>
<content:encoded><![CDATA[<p>Run <code>npx sdk</code> today.</p><h2>Deploy</h2>]]></content:encoded>
</item></channel></rss>"""
        (item,) = parse_cursor_feed(feed)
        assert item.tool is Tool.CURSOR
        assert item.version == "Agent SDK"
        assert item.published == date(2026, 10, 20)
        assert item.url == "https://cursor.com/changelog/agent-sdk"
        assert "Run npx sdk today." in item.notes
        assert "<p>" not in item.notes


class TestGrouping:
    def test_releases_are_grouped_per_tool_and_day(self) -> None:
        groups = group_releases(
            [
                release(version="2.1.317"),
                release(version="2.1.318"),
                release(Tool.CODEX, "0.166.0"),
                release(version="2.1.316", published=TODAY - timedelta(days=1)),
            ],
            today=TODAY,
            window_days=30,
        )
        claude_today = groups[(Tool.CLAUDE_CODE, TODAY)]
        assert claude_today.versions == ("2.1.317", "2.1.318")
        assert claude_today.url == "https://example.com/2.1.318"
        assert len(groups) == 3

    def test_old_releases_are_ignored(self) -> None:
        old = release(published=TODAY - timedelta(days=31))
        assert group_releases([old], today=TODAY, window_days=30) == {}

    def test_same_notes_are_not_summarized_again(self) -> None:
        group = group_releases([release()], today=TODAY, window_days=30)[(Tool.CLAUDE_CODE, TODAY)]
        current = record(source_hash=group.source_hash)
        assert not needs_tool_summary(current, group, "n1")
        assert needs_tool_summary(None, group, "n1")
        assert needs_tool_summary(current, group, "n2")
        assert needs_tool_summary(record(source_hash="b" * 64), group, "n1")

    def test_records_older_than_the_keep_window_are_dropped(self) -> None:
        records = {
            "claude-code:2026-11-04": record(),
            "claude-code:2026-08-01": record(day=date(2026, 8, 1)),
        }
        kept = prune_tool_updates(records, today=TODAY, keep_days=60)
        assert list(kept) == ["claude-code:2026-11-04"]


def news_request() -> ToolNewsRequest:
    return ToolNewsRequest(tool=Tool.CLAUDE_CODE, versions=("2.1.318",), notes="- Fixed --continue")


class TestWriter:
    def test_prompt_is_versioned_and_guards_against_copying(self) -> None:
        prompt = TOOL_NEWS_PROMPTS["n1"]
        assert "번역" in prompt
        assert "<release>" in prompt

    def test_korean_highlights_are_accepted(self, settings: Settings) -> None:
        line = "대화를 이어 할 때 앞 대화를 잃던 문제를 고쳤습니다."
        client, requests = anthropic_client({"relevant": True, "highlights": [line]})
        result = ClaudeToolNewsWriter(settings.news, client).write(news_request())
        assert result.highlights == (line,)
        assert "Fixed --continue" in requests[0]["messages"][0]["content"]

    def test_extra_highlights_are_cut_to_the_first_three(self, settings: Settings) -> None:
        lines = [f"{n}번째로 중요한 변경 사항을 사용자에게 알려 드립니다." for n in range(1, 6)]
        client, requests = anthropic_client({"relevant": True, "highlights": lines})
        result = ClaudeToolNewsWriter(settings.news, client).write(news_request())
        assert result.highlights == tuple(lines[:3])
        assert len(requests) == 1

    def test_nothing_relevant_is_a_valid_answer(self, settings: Settings) -> None:
        client, _ = anthropic_client({"relevant": False, "highlights": []})
        assert ClaudeToolNewsWriter(settings.news, client).write(news_request()).highlights == ()

    def test_english_highlights_are_rejected(self, settings: Settings) -> None:
        english = {"relevant": True, "highlights": ["Fixed --continue losing the conversation."]}
        client, _ = anthropic_client(*[english] * settings.news.validation_attempts)
        with pytest.raises(SummaryRejectedError):
            ClaudeToolNewsWriter(settings.news, client).write(news_request())


class ScriptedWriter:
    model = "scripted"

    def __init__(self) -> None:
        self.requests: list[ToolNewsRequest] = []

    def write(self, request: ToolNewsRequest) -> ToolNewsResult:
        self.requests.append(request)
        return ToolNewsResult(("새 기능을 더했습니다.",), 5, 1)


def test_pipeline_summarizes_new_groups_once_and_respects_the_cap(
    make_context: Callable[..., CollectContext],
) -> None:
    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("tool news must not call GitHub here")

    context = make_context(make_client(no_network))
    context.today = TODAY
    releases = [release(version=f"2.1.{n}", published=TODAY - timedelta(days=n)) for n in range(5)]
    capped = context.settings.news.model_copy(update={"max_calls_per_run": 3})
    context.settings = context.settings.model_copy(update={"news": capped})
    writer = ScriptedWriter()

    update_tool_news(context, writer, releases)
    update_tool_news(context, writer, releases)

    assert len(writer.requests) == 5
    assert len(context.state.tool_updates) == 5
    assert context.metrics.news_summarized == 5


def test_tool_updates_list_relevant_days_newest_first() -> None:
    state = CollectorState(
        tool_updates={
            "claude-code:2026-11-03": record(day=date(2026, 11, 3)),
            "codex:2026-11-04": record(tool=Tool.CODEX, versions=("0.166.0",)),
            "cursor:2026-11-04": record(tool=Tool.CURSOR, highlights=()),
        }
    )
    data = build_tool_updates_data(state)
    assert [(item.tool, item.date) for item in data.updates] == [
        (Tool.CODEX, date(2026, 11, 4)),
        (Tool.CLAUDE_CODE, date(2026, 11, 3)),
    ]
    assert isinstance(data.updates[0], SiteToolUpdate)
    assert "toolUpdates" not in build_news_data(state, SiteData()).model_dump(by_alias=True)


def test_tool_news_run_touches_only_its_own_files(
    make_context: Callable[..., CollectContext], tmp_path: Path
) -> None:
    """스킬 수집 워크플로와 커밋이 겹쳐도 충돌하지 않으려면 다른 파일을 바꾸면 안 된다."""

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("tool news must not call GitHub here")

    paths = Paths(
        tmp_path / "state",
        tmp_path,
        tmp_path / "skills.json",
        tmp_path / "samples",
        tmp_path / "news.json",
        tmp_path / "tool-updates.json",
    )
    context = make_context(make_client(no_network))
    context.today = TODAY
    context.state.star_history = {"acme/kit": {TODAY: 3}}
    save_state(context.state, paths.state)
    # 스킬 수집이 아직 새 형식으로 저장하지 않은 파일도 그대로 남아야 한다.
    (paths.state / "classifications.json").write_text('{"classifications": {}}', encoding="utf-8")
    before = {path.name: path.read_bytes() for path in paths.state.iterdir()}

    run_tool_news(context, ScriptedWriter(), [release()], paths)

    after = {path.name: path.read_bytes() for path in paths.state.iterdir()}
    changed = {name for name in after if after[name] != before.get(name)}
    assert changed == {"tool_updates.json"}
    assert (tmp_path / "tool-updates.json").exists()
    assert not (tmp_path / "news.json").exists()
