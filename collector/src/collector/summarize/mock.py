"""API 키 없이 파이프라인을 검증하기 위한 요약기. 결과는 실제 요약이 아니다."""

from collector.domain.models import Category, Difficulty, RecommendationTags, Role, Summary
from collector.summarize.base import SummaryRequest, SummaryResult

MOCK_MODEL = "mock"


class MockSummarizer:
    @property
    def model(self) -> str:
        return MOCK_MODEL

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        summary = Summary(
            summary_ko=f"[MOCK] {request.skill_name} 자리표시 요약입니다. 실제 요약이 아닙니다.",
            use_when=f"[MOCK] {request.skill_name} 동작을 확인할 때",
            category=Category.OTHER,
            tags=RecommendationTags(
                roles=(Role.GENERAL,), use_cases=("mock",), difficulty=Difficulty.BEGINNER
            ),
            runs_external_code=bool(request.bundled_files),
            accesses_network=False,
        )
        return SummaryResult(summary, input_tokens=0, output_tokens=0)
