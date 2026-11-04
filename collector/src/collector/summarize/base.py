"""요약기 인터페이스. 파이프라인은 Claude와 mock을 구분하지 않는다."""

from dataclasses import dataclass
from typing import Protocol

from collector.domain.models import ContentExclusion, Subcategory, Summary


@dataclass(frozen=True)
class SummaryRequest:
    skill_name: str
    repository: str
    path: str
    source: str
    bundled_files: tuple[str, ...]


@dataclass(frozen=True)
class SummaryResult:
    summary: Summary
    input_tokens: int
    output_tokens: int
    unverified_evidence: bool = False


class SummaryRejectedError(Exception):
    """이 입력으로는 쓸 수 있는 요약을 얻지 못했다. 기록하고 다음 스킬로 넘어간다."""

    def __init__(self, reason: str, input_tokens: int = 0, output_tokens: int = 0) -> None:
        super().__init__(reason)
        self.reason = reason
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class SummarizerUnavailableError(Exception):
    """서비스 쪽 문제다. 입력 탓이 아니므로 이번 실행의 요약만 멈추고 다음에 이어간다."""


class Summarizer(Protocol):
    @property
    def model(self) -> str: ...

    def summarize(self, request: SummaryRequest) -> SummaryResult: ...


@dataclass(frozen=True)
class ClassificationRequest:
    skill_name: str
    repository: str
    path: str
    summary_ko: str
    use_when: str
    use_cases: tuple[str, ...]


@dataclass(frozen=True)
class ClassificationResult:
    subcategory: Subcategory
    input_tokens: int
    output_tokens: int
    excluded: ContentExclusion | None = None


class Classifier(Protocol):
    """요약문만 읽고 세부 분류를 고른다. 실패는 요약기와 같은 두 예외로 알린다."""

    @property
    def model(self) -> str: ...

    def classify(self, request: ClassificationRequest) -> ClassificationResult: ...
