import hashlib
from collections.abc import Callable
from typing import Any

import pytest

from collector.config import ExcludeSettings, Settings
from collector.domain.models import (
    LEGACY_SUBCATEGORIES,
    SUBCATEGORY_PARENT,
    Category,
    ClassificationRecord,
    CollectorState,
    ContentExclusion,
    ExclusionReason,
    RepositoryRecord,
    Subcategory,
)
from collector.domain.summary_rules import needs_classification
from collector.export.site import build_site_data
from collector.pipeline.classify import classify_skills
from collector.pipeline.collect import CollectContext
from collector.summarize.base import (
    ClassificationRequest,
    ClassificationResult,
    SummarizerUnavailableError,
    SummaryRejectedError,
)
from collector.summarize.classify import ClaudeClassifier
from collector.summarize.classify_prompts import CLASSIFY_PROMPTS
from collector.summarize.prompts import V6_SUBCATEGORY_PARENT
from tests.test_summarize import (
    DAY,
    HASH_A,
    RANKING,
    anthropic_client,
    skill,
    stocked_context,
    summary_record,
)


def classification(**fields: Any) -> ClassificationRecord:
    values = {
        "subcategory": Subcategory.VIDEO,
        "taxonomy_version": "t1",
        "skill_md_hash": HASH_A,
        "summary_prompt_version": "v1",
        "model": "m",
    }
    return ClassificationRecord(**(values | fields))


class ScriptedClassifier:
    model = "scripted"

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[ClassificationRequest] = []

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if self.outcomes else Subcategory.VIDEO
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, ClassificationResult):
            return outcome
        return ClassificationResult(outcome, 7, 1)


def summarized_context(make_context: Callable[..., CollectContext], count: int) -> CollectContext:
    context = stocked_context(make_context, count)
    for key, record in context.state.skills.items():
        context.state.summaries[key] = summary_record(skill_md_hash=record.skill_md_hash)
    return context


class TestNeedsClassification:
    def test_new_summary_needs_one(self) -> None:
        assert needs_classification(skill(), summary_record(), None, "t1")

    def test_current_classification_is_kept(self) -> None:
        assert not needs_classification(skill(), summary_record(), classification(), "t1")

    def test_new_taxonomy_or_new_summary_needs_one_again(self) -> None:
        assert needs_classification(skill(), summary_record(), classification(), "t2")
        newer = summary_record(prompt_version="v6")
        assert needs_classification(skill(), newer, classification(), "t1")

    def test_skills_off_the_site_are_not_classified(self) -> None:
        excluded = skill(exclusion=ExclusionReason.FOREIGN_LANGUAGE)
        assert not needs_classification(excluded, summary_record(), None, "t1")
        assert not needs_classification(skill(), None, None, "t1")
        stale = summary_record(skill_md_hash="b" * 40)
        assert not needs_classification(skill(), stale, None, "t1")


def test_summaries_are_classified_once_from_their_own_text(
    make_context: Callable[..., CollectContext],
) -> None:
    context = summarized_context(make_context, 2)
    classifier = ScriptedClassifier(Subcategory.VIDEO, Subcategory.OFFICE)
    keys = list(context.state.skills)

    classify_skills(context, classifier, keys)
    classify_skills(context, classifier, keys)

    assert len(classifier.requests) == 2
    assert classifier.requests[0].summary_ko == summary_record().summary.summary_ko
    assert {record.subcategory for record in context.state.classifications.values()} == {
        Subcategory.VIDEO,
        Subcategory.OFFICE,
    }
    assert context.metrics.classified == 2
    assert context.metrics.classify_changed == 1  # 요약은 office를 골랐다


def test_rejected_classification_falls_back_and_outage_stops_new_calls(
    make_context: Callable[..., CollectContext],
) -> None:
    context = summarized_context(make_context, 6)
    summary_settings = context.settings.classify.model_copy(update={"concurrency": 1})
    context.settings = context.settings.model_copy(update={"classify": summary_settings})
    classifier = ScriptedClassifier(
        SummaryRejectedError("schema", 3, 1), SummarizerUnavailableError("503")
    )

    classify_skills(context, classifier, list(context.state.skills))

    assert len(classifier.requests) == 2
    assert context.state.classifications == {}
    assert context.metrics.classify_failed == 1


def test_run_cap_defers_the_rest(make_context: Callable[..., CollectContext]) -> None:
    context = summarized_context(make_context, 5)
    capped = context.settings.classify.model_copy(update={"max_calls_per_run": 2})
    context.settings = context.settings.model_copy(update={"classify": capped})

    classify_skills(context, ScriptedClassifier(), list(context.state.skills))

    assert len(context.state.classifications) == 2
    assert context.metrics.classify_skipped_by_cap == 3


def site_state() -> CollectorState:
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
    state.skills["acme/kit:a/SKILL.md"] = skill(path="a/SKILL.md")
    state.summaries["acme/kit:a/SKILL.md"] = summary_record()
    return state


def test_export_uses_the_classification_of_the_current_summary() -> None:
    state = site_state()
    state.classifications["acme/kit:a/SKILL.md"] = classification()

    exported = build_site_data(state, RANKING).skills[0]

    assert exported.subcategory == Subcategory.VIDEO
    assert exported.category == Category.DESIGN


def test_export_falls_back_when_the_summary_changed_since() -> None:
    state = site_state()
    state.classifications["acme/kit:a/SKILL.md"] = classification(summary_prompt_version="v0")

    exported = build_site_data(state, RANKING).skills[0]

    assert exported.subcategory == Subcategory.OFFICE
    assert exported.category == Category.DOCUMENTS


def test_claude_classifier_reads_the_summary_and_parses_the_choice(settings: Settings) -> None:
    client, requests = anthropic_client({"subcategory": "video"})
    request = ClassificationRequest(
        skill_name="hyperframes",
        repository="acme/kit",
        path="SKILL.md",
        summary_ko="HTML로 영상을 만들어 MP4로 렌더링합니다.",
        use_when="영상",
        use_cases=(),
    )

    result = ClaudeClassifier(settings.classify, client).classify(request)

    assert result.subcategory == Subcategory.VIDEO
    assert "HTML로 영상을 만들어" in requests[0]["messages"][0]["content"]
    assert requests[0]["model"] == settings.classify.model


# 기록에 남은 분류 기준은 내용이 바뀌면 안 된다. 바꾸려면 새 버전을 만든다.
RELEASED_TAXONOMY_HASHES = {"t1": "5fc47286966d"}


def test_released_taxonomies_never_change() -> None:
    for version, expected in RELEASED_TAXONOMY_HASHES.items():
        digest = hashlib.sha256(CLASSIFY_PROMPTS[version].encode()).hexdigest()[:12]
        assert digest == expected, version


def section_of(prompt: str, line: str) -> str:
    before = prompt[: prompt.index(line)]
    return max(Category, key=lambda category: before.rfind(f"\n- {category.value}:")).value


def test_t1_lists_the_taxonomy_it_was_released_with() -> None:
    prompt = CLASSIFY_PROMPTS["t1"]
    for subcategory, parent in V6_SUBCATEGORY_PARENT.items():
        line = f"\n  - {subcategory.value}: "
        assert prompt.count(line) == 1
        assert section_of(prompt, line) == parent.value
    assert "\n- finance:" not in prompt


def test_t2_lists_every_current_subcategory_under_its_category() -> None:
    prompt = CLASSIFY_PROMPTS["t2"]
    for subcategory, parent in SUBCATEGORY_PARENT.items():
        line = f"\n  - {subcategory.value}: "
        if subcategory in LEGACY_SUBCATEGORIES:
            assert line not in prompt
            continue
        assert prompt.count(line) == 1
        assert section_of(prompt, line) == parent.value


def test_t2_explains_when_to_exclude() -> None:
    prompt = CLASSIFY_PROMPTS["t2"]
    assert "placeholder" in prompt
    assert "demo" in prompt
    assert "foreign_region" in prompt
    assert "한국" in prompt
    assert "확실하지 않으면 null" in prompt


def test_claude_classifier_parses_a_foreign_region(settings: Settings) -> None:
    t2 = settings.classify.model_copy(update={"taxonomy_version": "t2"})
    client, _ = anthropic_client({"subcategory": "accounting-tax", "exclude": "foreign_region"})

    result = ClaudeClassifier(t2, client).classify(classify_request())

    assert result.excluded is ContentExclusion.FOREIGN_REGION


def test_legacy_subcategories_belong_to_the_new_categories() -> None:
    assert SUBCATEGORY_PARENT[Subcategory.FINANCE] is Category.FINANCE
    assert SUBCATEGORY_PARENT[Subcategory.AUDIO] is Category.AUDIO
    assert SUBCATEGORY_PARENT[Subcategory.LEGAL] is Category.LEGAL
    assert SUBCATEGORY_PARENT[Subcategory.HEALTH] is Category.HEALTH_LIFESTYLE
    assert SUBCATEGORY_PARENT[Subcategory.LIFESTYLE] is Category.HEALTH_LIFESTYLE


def classify_request() -> ClassificationRequest:
    return ClassificationRequest(
        skill_name="time-skill",
        repository="acme/kit",
        path="SKILL.md",
        summary_ko="파키스탄 표준시의 현재 시각을 보여 줍니다.",
        use_when="시각",
        use_cases=(),
    )


def test_claude_classifier_parses_an_exclusion(settings: Settings) -> None:
    t2 = settings.classify.model_copy(update={"taxonomy_version": "t2"})
    client, _ = anthropic_client({"subcategory": "misc", "exclude": "demo"})

    result = ClaudeClassifier(t2, client).classify(classify_request())

    assert result.subcategory == Subcategory.MISC
    assert result.excluded is ContentExclusion.DEMO


def test_t2_classifier_rejects_a_legacy_subcategory(settings: Settings) -> None:
    t2 = settings.classify.model_copy(update={"taxonomy_version": "t2"})
    legacy = {"subcategory": "finance", "exclude": None}
    client, requests = anthropic_client(*[legacy] * t2.validation_attempts)

    with pytest.raises(SummaryRejectedError, match="legacy"):
        ClaudeClassifier(t2, client).classify(classify_request())
    assert len(requests) == t2.validation_attempts


def test_exclusions_are_recorded(make_context: Callable[..., CollectContext]) -> None:
    context = summarized_context(make_context, 1)
    excluded = ClassificationResult(Subcategory.MISC, 7, 1, ContentExclusion.PLACEHOLDER)

    classify_skills(context, ScriptedClassifier(excluded), list(context.state.skills))

    record = next(iter(context.state.classifications.values()))
    assert record.excluded is ContentExclusion.PLACEHOLDER
    assert context.metrics.classify_excluded == 1


KEY = "acme/kit:a/SKILL.md"


def test_export_leaves_out_skills_judged_empty_or_demo() -> None:
    state = site_state()
    state.classifications[KEY] = classification(excluded=ContentExclusion.DEMO)

    assert build_site_data(state, RANKING).skills == ()


def test_keep_list_overrides_the_judgement() -> None:
    state = site_state()
    state.classifications[KEY] = classification(excluded=ContentExclusion.DEMO)

    data = build_site_data(state, RANKING, ExcludeSettings(keep=(KEY,)))

    assert len(data.skills) == 1


def test_export_leaves_out_listed_repositories_and_skills() -> None:
    by_repository = ExcludeSettings(repositories=("Acme/Kit",))
    by_skill = ExcludeSettings(skills=(KEY,))

    assert build_site_data(site_state(), RANKING, by_repository).skills == ()
    assert build_site_data(site_state(), RANKING, by_skill).skills == ()


def test_legacy_subcategory_is_shown_under_its_new_category() -> None:
    state = site_state()
    state.classifications[KEY] = classification(subcategory=Subcategory.FINANCE)

    exported = build_site_data(state, RANKING).skills[0]

    assert exported.category == Category.FINANCE
