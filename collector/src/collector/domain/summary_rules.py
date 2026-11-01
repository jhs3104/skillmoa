"""요약을 다시 만들지, 받은 요약을 믿을지를 정하는 규칙."""

import re

from collector.domain.models import SkillRecord, Summary, SummaryFailure, SummaryRecord

COPIED_FRAGMENT_CHARS = 30
_WHITESPACE = re.compile(r"\s+")


def needs_summary(
    skill: SkillRecord,
    record: SummaryRecord | None,
    failure: SummaryFailure | None,
    prompt_version: str,
    *,
    refresh_prompt: bool = False,
) -> bool:
    """해시가 바뀐 스킬만 재요약한다. 프롬프트 교체 재요약은 비용이 들어 명시적으로만 한다."""
    if skill.exclusion is not None:
        return False
    if (
        failure is not None
        and failure.skill_md_hash == skill.skill_md_hash
        and failure.prompt_version == prompt_version
    ):
        return False
    if record is None or record.skill_md_hash != skill.skill_md_hash:
        return True
    return refresh_prompt and record.prompt_version != prompt_version


def find_copied_fragment(summary: Summary, source: str) -> str | None:
    """원문과 연속으로 겹치는 구간을 찾는다. 번역은 못 잡지만 복사는 기계적으로 막는다."""
    normalized_source = _normalize(source)
    for text in (summary.summary_ko, summary.use_when):
        normalized = _normalize(text)
        for start in range(max(0, len(normalized) - COPIED_FRAGMENT_CHARS + 1)):
            fragment = normalized[start : start + COPIED_FRAGMENT_CHARS]
            if fragment in normalized_source:
                return fragment
    return None


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().lower()
