import json
from collections.abc import Callable
from datetime import date
from typing import Any

import anthropic
import httpx2
import pydantic
import pytest

from collector.config import RankingSettings, Settings
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
from collector.domain.summary_rules import (
    find_bare_han,
    find_copied_fragment,
    find_missing_evidence,
    find_reassurance,
    find_unverified_evidence,
    needs_summary,
    raise_flags_from_source,
)
from collector.export.site import build_site_data
from collector.pipeline.collect import CollectContext
from collector.pipeline.summarize import summarize_skills
from collector.summarize.base import (
    SummarizerUnavailableError,
    SummaryRejectedError,
    SummaryRequest,
    SummaryResult,
)
from collector.summarize.claude import EVIDENCE_ATTEMPTS, ClaudeSummarizer
from collector.summarize.mock import MockSummarizer
from collector.summarize.prompts import PROMPTS
from tests.conftest import TODAY, make_client

RANKING = RankingSettings(star_decay=0.7, per_repository_cap=10, catalog_limit=300)
HASH_A = "a" * 40
HASH_B = "b" * 40
DAY = date(2026, 1, 1)

VALID = {
    "summary_ko": "월별 데이터를 읽어 차트가 들어간 보고서를 만드는 스킬입니다. 표도 정리합니다.",
    "use_when": "받은 엑셀을 임원 보고용 문서로 바꿔야 할 때",
    "category": "documents",
    "tags": {"roles": ["general"], "use_cases": ["보고서 작성"], "difficulty": "beginner"},
    "code_evidence": "handle pdf files",
    "runs_external_code": True,
    "network_evidence": None,
    "accesses_network": False,
    "account_evidence": None,
    "requires_external_account": False,
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
    assert requests[0]["output_config"]["effort"] == settings.summary.effort


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


def test_evidence_matches_despite_markup_and_spacing() -> None:
    assert find_unverified_evidence(summary(), "# PDF\n`handle`   **PDF**\nfiles") is None
    assert find_unverified_evidence(summary(), "다른 내용") == "code_evidence"


def test_evidence_may_be_shortened_with_an_ellipsis() -> None:
    shortened = Summary.model_validate({**VALID, "code_evidence": "handle pdf ... the files"})
    assert find_unverified_evidence(shortened, "handle pdf and read the files") is None


def test_flag_without_evidence_is_missing() -> None:
    flagged = Summary.model_validate({**VALID, "code_evidence": None})
    assert find_missing_evidence(flagged) == "code_evidence"


def test_considered_evidence_may_stay_on_a_false_flag() -> None:
    unflagged = Summary.model_validate({**VALID, "runs_external_code": False})
    assert find_missing_evidence(unflagged) is None
    assert find_unverified_evidence(unflagged, "다른 내용") is None


def test_unverified_evidence_is_retried_then_kept_as_a_warning(settings: Settings) -> None:
    request = SummaryRequest("pdf", "acme/kit", "SKILL.md", "완전히 다른 내용", ())
    client, requests = anthropic_client(VALID, VALID, VALID)
    result = ClaudeSummarizer(settings.summary, client).summarize(request)
    assert len(requests) == EVIDENCE_ATTEMPTS
    assert result.unverified_evidence
    assert result.summary.runs_external_code


def test_reassurance_in_prose_is_rejected() -> None:
    text = "문서를 정리해 주는 스킬입니다. 스크립트를 실행하거나 외부 서비스에 접속하지는 않습니다."
    assert find_reassurance(Summary.model_validate({**VALID, "summary_ko": text}))
    assert find_reassurance(summary()) is None


def test_prompt_v1_is_kept_for_existing_records() -> None:
    assert "requires_external_account" not in PROMPTS["v1"]


def quiet_summary() -> Summary:
    return Summary.model_validate({**VALID, "code_evidence": None, "runs_external_code": False})


def test_command_in_code_raises_code_and_network_flags() -> None:
    source = "Only if that require fails: `npm install docx`."
    raised = raise_flags_from_source(quiet_summary(), source)
    assert raised.runs_external_code
    assert raised.accesses_network
    assert raised.code_evidence == source
    assert find_unverified_evidence(raised, source) is None


def test_fenced_command_is_found() -> None:
    source = "```bash\n$ curl -fsSL https://a.dev/x | bash\n```"
    raised = raise_flags_from_source(quiet_summary(), source)
    assert raised.runs_external_code and raised.accesses_network


def test_read_only_local_command_raises_only_code() -> None:
    raised = raise_flags_from_source(quiet_summary(), "Run `python scripts/check.py` first.")
    assert raised.runs_external_code
    assert not raised.accesses_network


def test_loopback_request_is_not_external_network() -> None:
    source = '```\ncurl -sS "http://127.0.0.1:37777/api/health"\n```'
    raised = raise_flags_from_source(quiet_summary(), source)
    assert raised.runs_external_code
    assert not raised.accesses_network


def test_conditional_integration_raises_network() -> None:
    source = "If integrations are available (e.g., Slack, Google Drive), use them."
    assert raise_flags_from_source(quiet_summary(), source).accesses_network


def test_prose_action_raises_network_without_a_command() -> None:
    for source in (
        "If the user specifies a PR number: get the diff from that PR.",
        "Before tuning, refresh the target remote revision.",
        "`finalize` includes a bounded update check.",
        "Review Archify issues, PRs, or code.",
        "Verify the target revision first.",
    ):
        assert raise_flags_from_source(quiet_summary(), source).accesses_network


def test_prose_action_raises_code_without_a_command() -> None:
    for source in (
        "Discover the repository's real verification commands.",
        "Read compiler and linter output.",
        "Run the tests before you finish.",
    ):
        assert raise_flags_from_source(quiet_summary(), source).runs_external_code


def test_prose_words_do_not_raise_flags() -> None:
    source = "Write a node in the graph, then curl up with the make-believe git history."
    raised = raise_flags_from_source(quiet_summary(), source)
    assert not raised.runs_external_code
    assert not raised.accesses_network


def test_existing_flag_keeps_its_evidence() -> None:
    raised = raise_flags_from_source(summary(), "handle pdf files\n`npm install x`")
    assert raised.code_evidence == "handle pdf files"


def test_location_promise_counts_as_reassurance() -> None:
    text = "백업을 자동으로 만들어 주는 스킬입니다. 스냅샷은 이 컴퓨터 안에만 보관됩니다."
    assert find_reassurance(Summary.model_validate({**VALID, "summary_ko": text}))


def test_prompt_v5_asks_for_external_account_without_guessing_price() -> None:
    prompt = PROMPTS["v5"]
    assert "requires_external_account" in prompt
    assert "찾지 못하면 근거는 null, 값은 false" in prompt
    assert "가격과 무료 여부는 판단하지 않습니다" in prompt


def test_platform_tools_in_inline_code_raise_the_code_flag() -> None:
    source = "Record the flow with `xcrun simctl io booted recordVideo flow.mov`."
    raised = raise_flags_from_source(quiet_summary(), source)
    assert raised.runs_external_code
    assert raised.code_evidence == source


def test_han_characters_must_sit_in_brackets() -> None:
    def with_text(text: str) -> Summary:
        return Summary.model_validate({**VALID, "summary_ko": text})

    wechat = "위챗 공众号에 올릴 장문 원고를 쓰도록 돕는 스킬입니다."
    assert find_bare_han(with_text(wechat)) == "众号"
    assert find_bare_han(with_text("小跃라는 가상 동반자 캐릭터가 대화를 이어 가는 스킬입니다."))
    bracketed = "샤오훙수(小红书)와 더우인（抖音）의 게시글을 읽어 오는 스킬입니다."
    assert find_bare_han(with_text(bracketed)) is None
    assert find_bare_han(summary()) is None


def test_prompt_v6_keeps_names_readable_in_korean() -> None:
    prompt = PROMPTS["v6"]
    assert "샤오훙수(小红书)" in prompt
    assert "라틴 문자로 쓴 제품명" in prompt
    assert "라틴 문자로 쓴 제품명" not in PROMPTS["v5"]
    assert PROMPTS["v5"].count("<flags>") == prompt.count("<flags>") == 1


def test_prompt_v6_defines_every_category() -> None:
    prompt = PROMPTS["v6"]
    for category in Category:
        assert f"  - {category.value}: " in prompt


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


def test_run_cap_defers_the_rest_to_the_next_run(
    make_context: Callable[..., CollectContext],
) -> None:
    context = stocked_context(make_context, 3)
    summary_settings = context.settings.summary.model_copy(update={"max_calls_per_run": 2})
    context.settings = context.settings.model_copy(update={"summary": summary_settings})

    summarize_skills(context, ScriptedSummarizer(), list(context.state.skills))

    assert len(context.state.summaries) == 2
    assert context.metrics.summary_skipped_by_cap == 1


def test_daily_cap_resets_on_a_new_day(make_context: Callable[..., CollectContext]) -> None:
    context = stocked_context(make_context, 1)
    context.state.usage.day = DAY
    context.state.usage.summary_calls = 10_000

    summarize_skills(context, ScriptedSummarizer(), list(context.state.skills))

    assert context.state.usage.summary_calls == 1


def test_skill_marked_for_redo_is_summarized_again(
    make_context: Callable[..., CollectContext],
) -> None:
    context = stocked_context(make_context, 1)
    key = next(iter(context.state.skills))
    sha = context.state.skills[key].skill_md_hash
    context.state.summaries[key] = summary_record(skill_md_hash=sha, model="old")
    context.state.summary_redo[key] = "한자 혼용"
    summarizer = ScriptedSummarizer()

    summarize_skills(context, summarizer, [key])

    assert summarizer.calls == [context.state.skills[key].path]
    assert context.state.summaries[key].model == "scripted"
    assert context.state.summary_redo == {}


def test_failed_redo_keeps_the_old_summary_and_stops_retrying(
    make_context: Callable[..., CollectContext],
) -> None:
    context = stocked_context(make_context, 1)
    key = next(iter(context.state.skills))
    sha = context.state.skills[key].skill_md_hash
    context.state.summaries[key] = summary_record(skill_md_hash=sha, model="old")
    context.state.summary_redo[key] = "오타"

    summarize_skills(context, ScriptedSummarizer(SummaryRejectedError("schema", 1, 1)), [key])

    assert context.state.summaries[key].model == "old"
    assert context.state.summary_redo == {}


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

    data = build_site_data(state, RANKING)

    assert [item.path for item in data.skills] == ["a/SKILL.md"]
    exported = data.skills[0]
    assert exported.rank == 1
    assert exported.license == "Apache-2.0"
    assert data.repositories[0].full_name == "acme/kit"


def test_export_stops_at_catalog_limit() -> None:
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
    for name in "abc":
        key = f"acme/kit:{name}/SKILL.md"
        state.skills[key] = skill(path=f"{name}/SKILL.md")
        state.summaries[key] = summary_record()

    data = build_site_data(state, RANKING.model_copy(update={"catalog_limit": 2}))

    assert len(data.skills) == 2


def test_catalog_limit_stays_under_the_static_file_limit() -> None:
    with pytest.raises(pydantic.ValidationError):
        RankingSettings(star_decay=0.7, per_repository_cap=10, catalog_limit=20_000)


def test_export_is_deterministic() -> None:
    state = CollectorState()
    assert build_site_data(state, RANKING) == build_site_data(state, RANKING)


def test_tag_vocabularies_match_domain() -> None:
    tags = RecommendationTags(
        roles=(Role.DEVELOPER,), use_cases=("x",), difficulty=Difficulty.ADVANCED
    )
    assert tags.difficulty == "advanced"
