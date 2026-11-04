"""도구 업데이트를 Claude로 요약한다 (ADR-0022)."""

import logging
import re

import anthropic
import pydantic
from pydantic import BaseModel, Field

from collector.config import NewsSettings
from collector.domain.models import Tool
from collector.summarize.base import (
    SummarizerUnavailableError,
    SummaryRejectedError,
    ToolNewsRequest,
    ToolNewsResult,
)
from collector.summarize.tool_news_prompts import TOOL_NEWS_PROMPTS

logger = logging.getLogger(__name__)

SDK_MAX_RETRIES = 3
MAX_HIGHLIGHTS = 3
MAX_HIGHLIGHT_CHARS = 140
# 한국어 문장이면 한글이 이만큼은 있다. 영어 원문을 그대로 옮긴 답을 거른다.
MIN_HANGUL_PER_HIGHLIGHT = 10
_HANGUL = re.compile(r"[가-힣]")

TOOL_NAMES = {Tool.CLAUDE_CODE: "Claude Code", Tool.CODEX: "Codex", Tool.CURSOR: "Cursor"}


class _Answer(BaseModel):
    relevant: bool
    highlights: list[str] = Field(default_factory=list)


class ClaudeToolNewsWriter:
    def __init__(self, settings: NewsSettings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._system = TOOL_NEWS_PROMPTS[settings.prompt_version]
        self._client = client or anthropic.Anthropic(
            timeout=settings.timeout_seconds, max_retries=SDK_MAX_RETRIES
        )

    @property
    def model(self) -> str:
        return self._settings.model

    def write(self, request: ToolNewsRequest) -> ToolNewsResult:
        input_tokens = 0
        output_tokens = 0
        reason = "no attempt"
        for attempt in range(1, self._settings.validation_attempts + 1):
            try:
                response = self._call(request)
            except pydantic.ValidationError as error:
                reason = f"schema: {error.error_count()} errors"
                continue
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            answer = response.parsed_output
            if response.stop_reason != "end_turn" or answer is None:
                reason = f"stop_reason: {response.stop_reason}"
                continue
            if not answer.relevant:
                return ToolNewsResult((), input_tokens, output_tokens)
            problem = _find_problem(answer.highlights)
            if problem is None:
                highlights = tuple(line.strip() for line in answer.highlights)
                return ToolNewsResult(highlights, input_tokens, output_tokens)
            reason = problem
            logger.info("업데이트 요약 재시도 %d회차 %s: %s", attempt, request.tool.value, reason)
        raise SummaryRejectedError(reason, input_tokens, output_tokens)

    def _call(self, request: ToolNewsRequest) -> anthropic.types.ParsedMessage[_Answer]:
        try:
            return self._client.messages.parse(
                model=self._settings.model,
                max_tokens=self._settings.max_output_tokens,
                system=self._system,
                messages=[{"role": "user", "content": self._render(request)}],
                output_format=_Answer,
                output_config={"effort": self._settings.effort},
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            raise
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as error:
            raise SummarizerUnavailableError(str(error)) from error

    def _render(self, request: ToolNewsRequest) -> str:
        notes = request.notes[: self._settings.max_source_chars]
        return (
            f"도구: {TOOL_NAMES[request.tool]}\n"
            f"버전: {', '.join(request.versions)}\n\n"
            f"<release>\n{notes}\n</release>"
        )


def _find_problem(highlights: list[str]) -> str | None:
    if not highlights:
        return "relevant without highlights"
    if len(highlights) > MAX_HIGHLIGHTS:
        return "too many highlights"
    for line in highlights:
        if len(line.strip()) > MAX_HIGHLIGHT_CHARS:
            return "highlight too long"
        if len(_HANGUL.findall(line)) < MIN_HANGUL_PER_HIGHLIGHT:
            return "not written in Korean"
    return None
