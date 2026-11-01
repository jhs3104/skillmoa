"""Claude API 요약기."""

import logging

import anthropic
import pydantic

from collector.config import SummarySettings
from collector.domain.models import Summary
from collector.domain.summary_rules import find_copied_fragment
from collector.summarize.base import (
    SummarizerUnavailableError,
    SummaryRejectedError,
    SummaryRequest,
    SummaryResult,
)
from collector.summarize.prompts import PROMPTS

logger = logging.getLogger(__name__)

SDK_MAX_RETRIES = 3


class ClaudeSummarizer:
    def __init__(
        self, settings: SummarySettings, client: anthropic.Anthropic | None = None
    ) -> None:
        self._settings = settings
        self._system = PROMPTS[settings.prompt_version]
        self._client = client or anthropic.Anthropic(
            timeout=settings.timeout_seconds, max_retries=SDK_MAX_RETRIES
        )

    @property
    def model(self) -> str:
        return self._settings.model

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        """형식이 틀리면 다시 요청하고, 끝까지 실패하면 SummaryRejectedError를 낸다."""
        input_tokens = 0
        output_tokens = 0
        reason = "no attempt"
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
            elif find_copied_fragment(summary, request.source):
                reason = "copied from source"
            else:
                return SummaryResult(summary, input_tokens, output_tokens)
            logger.info("요약 거부 %d회차 %s: %s", attempt, request.path, reason)
        raise SummaryRejectedError(reason, input_tokens, output_tokens)

    def _call(self, request: SummaryRequest) -> anthropic.types.ParsedMessage[Summary]:
        try:
            return self._client.messages.parse(
                model=self._settings.model,
                max_tokens=self._settings.max_output_tokens,
                system=self._system,
                messages=[{"role": "user", "content": _render(request)}],
                output_format=Summary,
                output_config={"effort": "low"},
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            raise
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as error:
            raise SummarizerUnavailableError(str(error)) from error


def _render(request: SummaryRequest) -> str:
    files = "\n".join(f"- {name}" for name in request.bundled_files) or "(없음)"
    return (
        f"스킬 이름: {request.skill_name}\n"
        f"저장소: {request.repository}\n"
        f"경로: {request.path}\n\n"
        f"함께 배포되는 파일:\n{files}\n\n"
        f"<skill_md>\n{request.source}\n</skill_md>"
    )
