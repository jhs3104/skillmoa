import json
from collections.abc import Callable
from datetime import date
from typing import Any

import anthropic
import httpx2
import pytest

from collector.config import Settings
from collector.domain.models import (
    Category,
    CollectorState,
    Difficulty,
    ExclusionReason,
    RecommendationTags,
    RepositoryRecord,
    Role,
    SkillRecord,
    Summary,
    SummaryFailure,
    SummaryRecord,
)
from collector.domain.summary_rules import find_copied_fragment, needs_summary
from collector.export.site import build_site_data
from collector.pipeline.collect import CollectContext
from collector.pipeline.summarize import summarize_skills
from collector.summarize.base import (
    SummarizerUnavailableError,
    SummaryRejectedError,
    SummaryRequest,
    SummaryResult,
)
from collector.summarize.claude import ClaudeSummarizer
from collector.summarize.mock import MockSummarizer
from collector.summarize.prompts import PROMPTS
from tests.conftest import TODAY, make_client

HASH_A = "a" * 40
HASH_B = "b" * 40
DAY = date(2026, 1, 1)

VALID = {
    "summary_ko": "월별 데이터를 읽어 차트가 들어간 보고서를 만드는 스킬입니다. 표 정리도 함께 합니다.",
    "use_when": "받은 엑셀을 임원 보고용 문서로 바꿔야 할 때",
    "category": "documents",
    "tags": {"roles": ["general"], "use_cases": ["보고서 작성"], "difficulty": "beginner"},
    "runs_external_code": True,
    "accesses_network": False,
}
REQUEST = SummaryRequest("pdf", "acme/kit", "skills/pdf/SKILL.md", "# PDF\nhandle pdf files", ())


def summary() -> Summary:
    return Summary.model_validate(VALID)


def skill(**fields: Any) -> SkillRecord:
    values = {
        "repository": "acme/kit",
        "path": "SKILL.md",
        "skill_md_hash": HASH_A,
        "name": "x",
        "first_seen_at": DAY,
        "last_seen_at": DAY,
    }
    return SkillRecord(**(values | fields))


def summary_record(**fields: Any) -> SummaryRecord:
    values = {
        "skill_md_hash": HASH_A,
        "prompt_version": "v1",
        "model": "m",
        "summary": summary(),
    }
    return SummaryRecord(**(values | fields))


def anthropic_client(*bodies: Any) -> tuple[anthropic.Anthropic, list[dict[str, Any]]]:
    """실제 SDK 경로(스키마 변환, 파싱)를 통과하도록 HTTP 계층만 대체한다."""
    requests: list[dict[str, Any]] = []
    queue = list(bodies)

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(json.loads(request.content))
        item = queue.pop(0)
        if isinstance(item, httpx2.Response):
            return item
        return httpx2.Response(200, json=message(item))

    http_client = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    return (
        anthropic.Anthropic(api_key="test", http_client=http_client, max_retries=0),
        requests,
    )


def message(content: Any, stop_reason: str = "end_turn") -> dict[str, Any]:
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def test_valid_response_is_parsed_into_the_domain_model(settings: Settings) -> None:
    client, requests = anthropic_client(VALID)
    result = ClaudeSummarizer(settings.summary, client).summarize(REQUEST)

    assert result.summary.category == Category.DOCUMENTS
    assert result.input_tokens == 100
    assert requests[0]["model"] == settings.summary.model
    assert requests[0]["output_config"]["format"]["type"] == "json_schema"
    assert requests[0]["output_config"]["effort"] == "low"


def test_source_is_passed_inside_the_data_block(settings: Settings) -> None:
    client, requests = anthropic_client(VALID)
    ClaudeSummarizer(settings.summary, client).summarize(REQUEST)
    content = requests[0]["messages"][0]["content"]
    assert "<skill_md>\n# PDF" in content


def test_invalid_output_is_retried(settings: Settings) -> None:
    client, requests = anthropic_client({"summary_ko": "짧음"}, VALID)
    result = ClaudeSummarizer(settings.summary, client).summarize(REQUEST)
    assert result.summary.summary_ko == VALID["summary_ko"]
    assert len(requests) == 2


def test_repeated_invalid_output_is_rejected(settings: Settings) -> None:
    client, requests = anthropic_client(*[{"bad": True}] * settings.summary.validation_attempts)
    with pytest.raises(SummaryRejectedError) as error:
        ClaudeSummarizer(settings.summary, client).summarize(REQUEST)
    assert error.value.reason.startswith("schema")
    assert len(requests) == settings.summary.validation_attempts


def test_refusal_is_rejected_without_crashing(settings: Settings) -> None:
    refusal = httpx2.Response(200, json=message(VALID, stop_reason="refusal"))
    again = httpx2.Response(200, json=message(VALID, stop_reason="refusal"))
    third = httpx2.Response(200, json=message(VALID, stop_reason="refusal"))
    client, _ = anthropic_client(refusal, again, third)
    with pytest.raises(SummaryRejectedError) as error:
        ClaudeSummarizer(settings.summary, client).summarize(REQUEST)
    assert error.value.reason == "stop_reason: refusal"
    assert error.value.input_tokens == 300


def test_copied_output_is_rejected(settings: Settings) -> None:
    source = VALID["summary_ko"]
    request = SummaryRequest("pdf", "acme/kit", "SKILL.md", source, ())
    client, _ = anthropic_client(VALID, VALID, VALID)
    with pytest.raises(SummaryRejectedError) as error:
        ClaudeSummarizer(settings.summary, client).summarize(request)
    assert error.value.reason == "copied from source"


def test_server_errors_are_reported_as_unavailable(settings: Settings) -> None:
    client, _ = anthropic_client(httpx2.Response(503, json={"type": "error"}))
    with pytest.raises(SummarizerUnavailableError):
        ClaudeSummarizer(settings.summary, client).summarize(REQUEST)


def test_authentication_errors_are_not_swallowed(settings: Settings) -> None:
    client, _ = anthropic_client(httpx2.Response(401, json={"type": "error"}))
    with pytest.raises(anthropic.AuthenticationError):
        ClaudeSummarizer(settings.summary, client).summarize(REQUEST)


def test_configured_prompt_version_exists(settings: Settings) -> None:
    assert settings.summary.prompt_version in PROMPTS


def test_new_skill_needs_summary() -> None:
    assert needs_summary(skill(), None, None, "v1")


def test_same_hash_is_not_summarized_again() -> None:
    assert not needs_summary(skill(), summary_record(), None, "v1")


def test_changed_hash_is_summarized_again() -> None:
    assert needs_summary(skill(skill_md_hash=HASH_B), summary_record(), None, "v1")


def test_new_prompt_version_alone_does_not_cost_money() -> None:
    assert not needs_summary(skill(), summary_record(), None, "v2")


def test_refresh_prompt_is_explicit() -> None:
    assert needs_summary(skill(), summary_record(), None, "v2", refresh_prompt=True)


def test_excluded_skill_is_never_summarized() -> None:
    assert not needs_summary(skill(exclusion=ExclusionReason.EMPTY), None, None, "v1")


def test_failure_is_not_retried_for_the_same_input() -> None:
    failure = SummaryFailure(skill_md_hash=HASH_A, prompt_version="v1", reason="x")
    assert not needs_summary(skill(), None, failure, "v1")


def test_failure_is_retried_after_the_prompt_changes() -> None:
    failure = SummaryFailure(skill_md_hash=HASH_A, prompt_version="v1", reason="x")
    assert needs_summary(skill(), None, failure, "v2")


def test_copy_detection_ignores_whitespace_and_case() -> None:
    fragment = VALID["summary_ko"][:40]
    source = "intro " + fragment.replace(" ", "\n  ").upper()
    assert find_copied_fragment(summary(), source)


def test_copy_detection_passes_original_text() -> None:
    assert find_copied_fragment(summary(), "완전히 다른 원문 내용입니다") is None


class ScriptedSummarizer:
    model = "scripted"

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[str] = []

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        self.calls.append(request.path)
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(outcome, Exception):
            raise outcome
        return SummaryResult(summary(), 10, 2)


def stocked_context(make_context: Callable[..., CollectContext], count: int) -> CollectContext:
    def handler(request: httpx2.Request) -> None:
        raise AssertionError("cached content must be used")

    context = make_context(make_client(handler))
    context.state.repositories["acme/kit"] = RepositoryRecord(
        github_id=1,
        owner="acme",
        name="kit",
        stars=5,
        pushed_at="2026-10-01T00:00:00Z",
        license="MIT",
        default_branch="main",
        first_seen_at=DAY,
    )
    for index in range(count):
        sha = f"{index:040x}"
        path = f"{index}/SKILL.md"
        context.state.skills[f"acme/kit:{path}"] = skill(path=path, skill_md_hash=sha)
        cache = context.content._cache
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{sha}.md").write_text("# body", encoding="utf-8")
    return context


def test_rejected_skill_is_recorded_and_the_run_continues(
    make_context: Callable[..., CollectContext],
) -> None:
    context = stocked_context(make_context, 2)
    summarizer = ScriptedSummarizer(SummaryRejectedError("schema", 5, 1))

    summarize_skills(context, summarizer, list(context.state.skills))

    assert len(context.state.summaries) == 1
    assert len(context.state.summary_failures) == 1
    assert context.metrics.summary_failed == 1
    assert context.metrics.input_tokens == 15


def test_service_outage_stops_without_recording_failures(
    make_context: Callable[..., CollectContext],
) -> None:
    context = stocked_context(make_context, 2)
    summarizer = ScriptedSummarizer(SummarizerUnavailableError("503"))

    summarize_skills(context, summarizer, list(context.state.skills))

    assert context.state.summary_failures == {}
    assert context.metrics.summary_aborted
    assert len(summarizer.calls) == 1


def test_daily_cap_defers_the_rest_to_the_next_run(
    make_context: Callable[..., CollectContext],
) -> None:
    context = stocked_context(make_context, 3)
    context.state.usage.day = TODAY
    context.state.usage.summary_calls = context.settings.summary.max_calls_per_day - 1

    summarize_skills(context, ScriptedSummarizer(), list(context.state.skills))

    assert len(context.state.summaries) == 1
    assert context.metrics.summary_skipped_by_cap == 2


def test_daily_cap_resets_on_a_new_day(make_context: Callable[..., CollectContext]) -> None:
    context = stocked_context(make_context, 1)
    context.state.usage.day = DAY
    context.state.usage.summary_calls = 10_000

    summarize_skills(context, ScriptedSummarizer(), list(context.state.skills))

    assert context.state.usage.summary_calls == 1


def test_oversized_source_is_recorded_not_truncated(
    make_context: Callable[..., CollectContext],
) -> None:
    context = stocked_context(make_context, 1)
    key = next(iter(context.state.skills))
    sha = context.state.skills[key].skill_md_hash
    limit = context.settings.summary.max_source_chars
    (context.content._cache / f"{sha}.md").write_text("x" * (limit + 1), encoding="utf-8")
    summarizer = ScriptedSummarizer()

    summarize_skills(context, summarizer, [key])

    assert summarizer.calls == []
    assert context.state.summary_failures[key].reason == "source too long"


def test_mock_output_is_marked_as_mock() -> None:
    result = MockSummarizer().summarize(REQUEST)
    assert result.summary.summary_ko.startswith("[MOCK]")


def test_export_contains_only_summarized_skills_with_fresh_hash() -> None:
    state = CollectorState(bootstrapped_on=DAY)
    state.repositories["acme/kit"] = RepositoryRecord(
        github_id=1,
        owner="acme",
        name="kit",
        stars=5,
        pushed_at="2026-10-01T00:00:00Z",
        license="MIT",
        default_branch="main",
        first_seen_at=DAY,
    )
    state.skills["acme/kit:a/SKILL.md"] = skill(path="a/SKILL.md", license="Apache-2.0")
    state.skills["acme/kit:b/SKILL.md"] = skill(path="b/SKILL.md", skill_md_hash=HASH_B)
    state.skills["acme/kit:c/SKILL.md"] = skill(path="c/SKILL.md", skill_md_hash="c" * 40)
    state.summaries["acme/kit:a/SKILL.md"] = summary_record()
    state.summaries["acme/kit:b/SKILL.md"] = summary_record()

    data = build_site_data(state, star_decay=0.7)

    assert [item.path for item in data.skills] == ["a/SKILL.md"]
    exported = data.skills[0]
    assert exported.rank == 1
    assert exported.license == "Apache-2.0"
    assert data.repositories[0].full_name == "acme/kit"


def test_export_is_deterministic() -> None:
    state = CollectorState()
    assert build_site_data(state, 0.7) == build_site_data(state, 0.7)


def test_tag_vocabularies_match_domain() -> None:
    tags = RecommendationTags(
        roles=(Role.DEVELOPER,), use_cases=("x",), difficulty=Difficulty.ADVANCED
    )
    assert tags.difficulty == "advanced"
