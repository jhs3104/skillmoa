"""요약을 다시 만들지, 받은 요약을 믿을지를 정하는 규칙."""

import re

from collector.domain.models import (
    MAX_EVIDENCE_CHARS,
    SUBCATEGORY_PARENT,
    SkillRecord,
    Summary,
    SummaryFailure,
    SummaryRecord,
)

COPIED_FRAGMENT_CHARS = 30
_WHITESPACE = re.compile(r"\s+")
_QUOTE_MARKUP = re.compile(r"[`*_\"'“”‘’]")
_ELLIPSIS = re.compile(r"\.{3,}|…")
_REASSURANCE = re.compile(
    r"안전합니다|안전하게 쓸|스크립트 없이|실행하지(는)? 않|접속하지(는)? 않|"
    r"네트워크 없이|외부 서비스 없이|설치 없이|무료로 쓸|무료입니다|"
    r"이 컴퓨터 안에|로컬에만|원문"
)
# 한국어 문장 속 한자·가나는 오타처럼 읽힌다. 괄호 안 병기만 허용한다.
_BRACKETED = re.compile(r"\([^()]*\)|（[^（）]*）")
_HAN_OR_KANA = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_FENCE = re.compile(r"^(`{3,}|~{3,}).*$")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_PROMPT = re.compile(r"^\s*(?:[$>#]\s+)?")
_LOCAL_COMMANDS = (
    r"python3?|node|bash|sh|zsh|make|cargo|go|docker|uv|deno|bun|ant|git|"
    r"xcrun|swift|ruby|php|java|osascript|ffmpeg|pytest|kubectl|terraform"
)
_NETWORK_COMMANDS = (
    r"npx|uvx|curl|wget|gh|git\s+(?:clone|pull|push|fetch)|"
    r"(?:npm|pnpm|yarn|pip3?|uv|cargo|brew|apt(?:-get)?)\s+(?:install|add|i)\b"
)
_NETWORK_COMMAND = re.compile(rf"(?:{_NETWORK_COMMANDS})(?:\s|$)")
_ANY_COMMAND = re.compile(rf"(?:{_NETWORK_COMMANDS}|(?:{_LOCAL_COMMANDS})\s)", re.IGNORECASE)
_LOOPBACK = re.compile(r"127\.0\.0\.1|localhost|\[::1\]", re.IGNORECASE)
_NETWORK_PROSE = re.compile(
    r"\bMCP\b|\bconnectors?\b|\bcloud sync\b|\bintegrations? (?:is|are) available\b|"
    r"\bappropriate integration\b|\bPR number\b|\bpull request number\b|"
    r"\bremote (?:revision|branch)\b|\bupdate check\b|\buser-provided URL\b|"
    r"\bPRs?\b|\bpull requests?\b|\btarget revision\b|\bissue triage\b"
)
_CODE_PROSE = re.compile(
    r"\bverification commands?\b|\bcompiler(?: and linter)? output\b|\blinter output\b|"
    r"\brun (?:the |all |your )?(?:tests?|linters?|builds?|compiler)\b|"
    r"\bversion-control state\b",
    re.IGNORECASE,
)


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


def find_missing_evidence(summary: Summary) -> str | None:
    """표시를 켰는데 근거가 없으면 칸 이름을 돌려준다."""
    for name, flag, evidence in _flags(summary):
        if flag and not evidence:
            return name
    return None


def find_unverified_evidence(summary: Summary, source: str) -> str | None:
    """켠 표시의 근거가 원문에서 확인되지 않으면 칸 이름을 돌려준다.

    꺼진 표시의 근거는 검토하다 제외한 구절일 수 있어 보지 않는다.
    """
    normalized_source = _strip_markup(source)
    for name, flag, evidence in _flags(summary):
        if not flag or not evidence:
            continue
        parts = [_strip_markup(part) for part in _ELLIPSIS.split(evidence)]
        if not all(part in normalized_source for part in parts if part):
            return name
    return None


def raise_flags_from_source(summary: Summary, source: str) -> Summary:
    """원문의 명령이나 연동 문구로 AI가 놓친 표시를 켠다. 끄지는 않는다.

    놓친 경고는 사용자에게 없는 것처럼 보이므로, 과하게 켜지는 쪽을 택한다.
    """
    code_line, network_line = _find_signal_lines(source)
    changes: dict[str, bool | str] = {}
    if code_line and not summary.runs_external_code:
        changes |= {"runs_external_code": True, "code_evidence": code_line}
    if network_line and not summary.accesses_network:
        changes |= {"accesses_network": True, "network_evidence": network_line}
    return summary.model_copy(update=changes) if changes else summary


def _find_signal_lines(source: str) -> tuple[str | None, str | None]:
    code_line: str | None = None
    network_line: str | None = None
    fenced = False
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if _FENCE.match(line):
            fenced = not fenced
            continue
        spans = [line] if fenced else _INLINE_CODE.findall(line)
        for span in spans:
            command = _PROMPT.sub("", span)
            if _ANY_COMMAND.match(command):
                code_line = code_line or _evidence_line(line)
            if _NETWORK_COMMAND.match(command) and not _LOOPBACK.search(command):
                network_line = network_line or _evidence_line(line)
        if not fenced and _NETWORK_PROSE.search(line):
            network_line = network_line or _evidence_line(line)
        if not fenced and _CODE_PROSE.search(line):
            code_line = code_line or _evidence_line(line)
    return code_line, network_line


def _evidence_line(line: str) -> str:
    return line[:MAX_EVIDENCE_CHARS]


def find_reassurance(summary: Summary) -> str | None:
    """표시로 전할 내용을 본문의 안심 문구로 쓰지 못하게 막는다."""
    for text in (summary.summary_ko, summary.use_when):
        match = _REASSURANCE.search(text)
        if match:
            return match.group()
    return None


def align_category(summary: Summary) -> Summary:
    """대분류를 세부 분류에 맞춘다. 모델이 둘을 어긋나게 골라도 목록에서 엇갈리지 않는다."""
    if summary.subcategory is None:
        return summary
    parent = SUBCATEGORY_PARENT[summary.subcategory]
    if summary.category is parent:
        return summary
    return summary.model_copy(update={"category": parent})


def find_bare_han(summary: Summary) -> str | None:
    """괄호 밖에 남은 한자·가나를 찾는다. 이름은 "샤오훙수(小红书)"처럼 한글 뒤에 병기해야 한다."""
    for text in (summary.summary_ko, summary.use_when, *summary.tags.use_cases):
        match = _HAN_OR_KANA.search(_BRACKETED.sub("", text))
        if match:
            return match.group()
    return None


def _flags(summary: Summary) -> tuple[tuple[str, bool, str | None], ...]:
    return (
        ("code_evidence", summary.runs_external_code, summary.code_evidence),
        ("network_evidence", summary.accesses_network, summary.network_evidence),
        ("account_evidence", summary.requires_external_account, summary.account_evidence),
    )


def _strip_markup(text: str) -> str:
    return _normalize(_QUOTE_MARKUP.sub("", text))


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().lower()
