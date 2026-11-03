"""Claude API 요약기."""

import logging

import anthropic
import pydantic

from collector.config import SummarySettings
from collector.domain.models import Summary
from collector.domain.summary_rules import (
    align_category,
    find_bare_han,
    find_copied_fragment,
    find_missing_evidence,
    find_reassurance,
    find_stray_letters,
    find_unverified_evidence,
    raise_flags_from_source,
)
from collector.summarize.base import (
    SummarizerUnavailableError,
    SummaryRejectedError,
    SummaryRequest,
    SummaryResult,
)
from collector.summarize.prompts import PROMPTS, asks_for_subcategory

logger = logging.getLogger(__name__)

SDK_MAX_RETRIES = 3
# 근거 인용만 어긋난 경우 다시 물어도 비슷한 답이 나온다. 표시는 유지되므로 한 번만 재시도한다.
EVIDENCE_ATTEMPTS = 2


class ClaudeSummarizer:
    def __init__(
        self, settings: SummarySettings, client: anthropic.Anthropic | None = None
    ) -> None:
        self._settings = settings
        self._system = PROMPTS[settings.prompt_version]
        self._needs_subcategory = asks_for_subcategory(settings.prompt_version)
        self._client = client or anthropic.Anthropic(
            timeout=settings.timeout_seconds, max_retries=SDK_MAX_RETRIES
        )

    @property
    def model(self) -> str:
        return self._settings.model

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        """형식이 틀리면 다시 요청하고, 끝까지 실패하면 SummaryRejectedError를 낸다.

        근거만 확인되지 않은 요약은 버리지 않는다. 켜진 경고를 스킬째 잃는 쪽이 더 위험하다.
        """
        input_tokens = 0
        output_tokens = 0
        reason = "no attempt"
        unverified: Summary | None = None
        for attempt in range(1, self._settings.validation_attempts + 1):
            try:
                response = self._call(request)
            except pydantic.ValidationError as error:
                reason = f"schema: {error.error_count()} errors"
                logger.info("형식 오류 %d회차 %s", attempt, request.path)
                continue

            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            summary = response.parsed_output
            if response.stop_reason != "end_turn":
                reason = f"stop_reason: {response.stop_reason}"
            elif summary is None:
                reason = "empty output"
            else:
                problem = _find_problem(summary, request.source, self._needs_subcategory)
                evidence_gap = find_unverified_evidence(summary, request.source)
                if problem is None and evidence_gap is None:
                    raised = raise_flags_from_source(align_category(summary), request.source)
                    return SummaryResult(raised, input_tokens, output_tokens)
                if problem is None:
                    unverified = summary
                reason = problem or f"unverified {evidence_gap}: {_quote(summary, evidence_gap)}"
            logger.info("요약 재시도 %d회차 %s: %s", attempt, request.path, reason)
            if unverified is not None and attempt >= EVIDENCE_ATTEMPTS:
                break
        if unverified is not None:
            logger.warning("근거 미확인으로 표시 유지 %s", request.path)
            raised = raise_flags_from_source(align_category(unverified), request.source)
            return SummaryResult(raised, input_tokens, output_tokens, unverified_evidence=True)
        raise SummaryRejectedError(reason, input_tokens, output_tokens)

    def _call(self, request: SummaryRequest) -> anthropic.types.ParsedMessage[Summary]:
        try:
            return self._client.messages.parse(
                model=self._settings.model,
                max_tokens=self._settings.max_output_tokens,
                system=self._system,
                messages=[{"role": "user", "content": _render(request)}],
                output_format=Summary,
                output_config={"effort": self._settings.effort},
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            raise
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as error:
            raise SummarizerUnavailableError(str(error)) from error


def _quote(summary: Summary, evidence_name: str | None) -> str:
    return (getattr(summary, evidence_name or "", None) or "")[:80]


def _find_problem(summary: Summary, source: str, needs_subcategory: bool) -> str | None:
    if needs_subcategory and summary.subcategory is None:
        return "missing subcategory"
    if find_copied_fragment(summary, source):
        return "copied from source"
    missing = find_missing_evidence(summary)
    if missing:
        return f"missing {missing}"
    if find_reassurance(summary):
        return "reassurance in prose"
    if find_bare_han(summary):
        return "han characters outside brackets"
    if find_stray_letters(summary):
        return "stray letters"
    return None


def _render(request: SummaryRequest) -> str:
    files = "\n".join(f"- {name}" for name in request.bundled_files) or "(없음)"
    return (
        f"스킬 이름: {request.skill_name}\n"
        f"저장소: {request.repository}\n"
        f"경로: {request.path}\n\n"
        f"함께 배포되는 파일:\n{files}\n\n"
        f"<skill_md>\n{request.source}\n</skill_md>"
    )
