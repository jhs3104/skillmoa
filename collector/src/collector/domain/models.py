"""Repository 1:N Skill 도메인 모델과 수집 상태 레코드."""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

STATE_SCHEMA_VERSION = 1
MAX_EVIDENCE_CHARS = 200

GitBlobSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
"""git tree의 blob SHA. 내용이 같으면 값도 같아서 SKILL.md 해시로 쓴다."""


class Category(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    DEVOPS = "devops"
    DATA = "data"
    DOCUMENTS = "documents"
    DESIGN = "design"
    WRITING = "writing"
    MARKETING = "marketing"
    PRODUCTIVITY = "productivity"
    RESEARCH = "research"
    SECURITY = "security"
    AI_AGENTS = "ai-agents"
    OTHER = "other"


class Role(StrEnum):
    """추천 질문의 직군 선택지와 같은 어휘를 쓴다."""

    DEVELOPER = "developer"
    DESIGNER = "designer"
    DATA = "data"
    PRODUCT = "product"
    MARKETER = "marketer"
    WRITER = "writer"
    RESEARCHER = "researcher"
    GENERAL = "general"


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ExclusionReason(StrEnum):
    FORK = "fork"
    TEST_REPOSITORY = "test_repository"
    TEST_PATH = "test_path"
    EMPTY = "empty"
    TOO_SHORT = "too_short"
    DUPLICATE = "duplicate"


class Repository(BaseModel):
    """GitHub에서 관찰한 저장소 사실. 스타는 이 단위에만 존재한다."""

    model_config = ConfigDict(frozen=True)

    github_id: int
    owner: str
    name: str
    stars: int = Field(ge=0)
    pushed_at: datetime
    license: str | None
    default_branch: str
    description: str | None = None
    is_fork: bool = False
    is_archived: bool = False

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class RepositoryRecord(Repository):
    """상태에 저장하는 저장소. 어디까지 스캔했는지를 함께 기억한다."""

    first_seen_at: date
    scanned_pushed_at: datetime | None = None
    exclusion: ExclusionReason | None = None
    sources: tuple[str, ...] = ()


class SkillRecord(BaseModel):
    """저장소 안의 SKILL.md 하나. 경로가 바뀌면 다른 스킬로 본다."""

    model_config = ConfigDict(frozen=True)

    repository: str
    path: str
    skill_md_hash: GitBlobSha
    name: str
    first_seen_at: date
    last_seen_at: date
    license: str | None = None
    exclusion: ExclusionReason | None = None
    bundled_files: tuple[str, ...] = ()


class RecommendationTags(BaseModel):
    model_config = ConfigDict(frozen=True)

    roles: tuple[Role, ...] = Field(min_length=1, max_length=3)
    use_cases: tuple[str, ...] = Field(min_length=1, max_length=5)
    difficulty: Difficulty


class Summary(BaseModel):
    """Claude가 생성한 한국어 요약. 원문의 번역이 아니라 새로 쓴 설명이다."""

    model_config = ConfigDict(frozen=True)

    summary_ko: str = Field(min_length=20, max_length=400)
    use_when: str = Field(min_length=10, max_length=200)
    category: Category
    tags: RecommendationTags
    code_evidence: str | None = Field(max_length=MAX_EVIDENCE_CHARS)
    runs_external_code: bool
    network_evidence: str | None = Field(max_length=MAX_EVIDENCE_CHARS)
    accesses_network: bool
    account_evidence: str | None = Field(max_length=MAX_EVIDENCE_CHARS)
    requires_external_account: bool


class SummaryRecord(BaseModel):
    """어떤 입력과 프롬프트로 요약했는지를 남겨 재요약 여부를 판단한다."""

    model_config = ConfigDict(frozen=True)

    skill_md_hash: GitBlobSha
    prompt_version: str
    model: str
    summary: Summary


class SummaryFailure(BaseModel):
    """같은 입력으로 재시도해도 실패한 기록. 해시나 프롬프트가 바뀌면 다시 시도한다."""

    model_config = ConfigDict(frozen=True)

    skill_md_hash: GitBlobSha
    prompt_version: str
    reason: str


class DailyUsage(BaseModel):
    day: date | None = None
    summary_calls: int = 0


class CollectorState(BaseModel):
    """collector/state/에 커밋되는 전체 상태."""

    schema_version: int = STATE_SCHEMA_VERSION
    bootstrapped_on: date | None = None
    usage: DailyUsage = DailyUsage()
    repositories: dict[str, RepositoryRecord] = {}
    skills: dict[str, SkillRecord] = {}
    summaries: dict[str, SummaryRecord] = {}
    summary_failures: dict[str, SummaryFailure] = {}
    # 검수에서 걸린 요약. 키는 스킬, 값은 사유. 다시 만들 때까지 기존 요약은 그대로 보여 준다.
    summary_redo: dict[str, str] = {}
