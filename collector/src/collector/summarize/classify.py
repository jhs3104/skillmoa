"""Claude로 세부 분류를 고른다 (ADR-0018)."""

import logging

import anthropic
import pydantic
from pydantic import BaseModel

from collector.config import ClassifySettings
from collector.domain.models import Subcategory
from collector.summarize.base import (
    ClassificationRequest,
    ClassificationResult,
    SummarizerUnavailableError,
    SummaryRejectedError,
)
from collector.summarize.classify_prompts import CLASSIFY_PROMPTS

logger = logging.getLogger(__name__)

SDK_MAX_RETRIES = 3


class _Choice(BaseModel):
    subcategory: Subcategory


class ClaudeClassifier:
    def __init__(
        self, settings: ClassifySettings, client: anthropic.Anthropic | None = None
    ) -> None:
        self._settings = settings
        self._system = CLASSIFY_PROMPTS[settings.taxonomy_version]
        self._client = client or anthropic.Anthropic(
            timeout=settings.timeout_seconds, max_retries=SDK_MAX_RETRIES
        )

    @property
    def model(self) -> str:
        return self._settings.model

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        input_tokens = 0
        output_tokens = 0
        reason = "no attempt"
        for attempt in range(1, self._settings.validation_attempts + 1):
            try:
                response = self._call(request)
            except pydantic.ValidationError as error:
                reason = f"schema: {error.error_count()} errors"
                logger.info("분류 형식 오류 %d회차 %s", attempt, request.path)
                continue
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            choice = response.parsed_output
            if response.stop_reason == "end_turn" and choice is not None:
                return ClassificationResult(choice.subcategory, input_tokens, output_tokens)
            reason = f"stop_reason: {response.stop_reason}"
        raise SummaryRejectedError(reason, input_tokens, output_tokens)

    def _call(self, request: ClassificationRequest) -> anthropic.types.ParsedMessage[_Choice]:
        try:
            return self._client.messages.parse(
                model=self._settings.model,
                max_tokens=self._settings.max_output_tokens,
                system=self._system,
                messages=[{"role": "user", "content": _render(request)}],
                output_format=_Choice,
                output_config={"effort": self._settings.effort},
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            raise
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as error:
            raise SummarizerUnavailableError(str(error)) from error


def _render(request: ClassificationRequest) -> str:
    use_cases = ", ".join(request.use_cases)
    return f"""<skill>
이름: {request.skill_name}
저장소: {request.repository}
경로: {request.path}
소개: {request.summary_ko}
이럴 때: {request.use_when}
용도: {use_cases}
</skill>"""
