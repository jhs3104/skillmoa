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
    # 기타에 많이 모인 주제를 꺼냈다 (ADR-0020).
    FINANCE = "finance"
    AUDIO = "audio"
    LEGAL = "legal"
    HEALTH_LIFESTYLE = "health-lifestyle"
    OTHER = "other"


class Subcategory(StrEnum):
    """대분류 아래의 세부 분류. 모델은 이것만 고르고 대분류는 SUBCATEGORY_PARENT로 정한다."""

    FRONTEND = "frontend"
    BACKEND = "backend"
    MOBILE = "mobile"
    GIT = "git"
    CODE_QUALITY = "code-quality"
    DEBUGGING = "debugging"
    DEV_TOOLS = "dev-tools"
    GAME_DEV = "game-dev"
    WEB3 = "web3"
    TEST_WRITING = "test-writing"
    BROWSER_TESTING = "browser-testing"
    QA = "qa"
    DEPLOYMENT = "deployment"
    INFRASTRUCTURE = "infrastructure"
    MONITORING = "monitoring"
    RELEASE = "release"
    DATA_ANALYSIS = "data-analysis"
    DATABASE = "database"
    MACHINE_LEARNING = "machine-learning"
    VISUALIZATION = "visualization"
    PDF = "pdf"
    OFFICE = "office"
    PRESENTATION = "presentation"
    DIAGRAM = "diagram"
    UI_UX = "ui-ux"
    VISUAL_DESIGN = "visual-design"
    IMAGE = "image"
    VIDEO = "video"
    ACCESSIBILITY = "accessibility"
    DRAFTING = "drafting"
    TRANSLATION = "translation"
    EDITING = "editing"
    SEO = "seo"
    SOCIAL_MEDIA = "social-media"
    ADVERTISING = "advertising"
    SALES = "sales"
    ECOMMERCE = "ecommerce"
    COMMUNICATION = "communication"
    NOTES_CALENDAR = "notes-calendar"
    PROJECT_MANAGEMENT = "project-management"
    AUTOMATION = "automation"
    LEARNING = "learning"
    WEB_RESEARCH = "web-research"
    ACADEMIC = "academic"
    MARKET_RESEARCH = "market-research"
    SECURITY_REVIEW = "security-review"
    VULNERABILITY = "vulnerability"
    AUTH = "auth"
    SKILL_AUTHORING = "skill-authoring"
    MCP = "mcp"
    AGENT_OPERATIONS = "agent-operations"
    AI_ENGINEERING = "ai-engineering"
    PERSONA = "persona"
    INVESTING = "investing"
    FINANCIAL_ANALYSIS = "financial-analysis"
    ACCOUNTING_TAX = "accounting-tax"
    SPEECH = "speech"
    MUSIC = "music"
    SOUND = "sound"
    CONTRACTS = "contracts"
    COMPLIANCE = "compliance"
    LEGAL_WORK = "legal-work"
    HEALTH = "health"
    LIFESTYLE = "lifestyle"
    BUSINESS_OPS = "business-ops"
    MISC = "misc"
    # t1까지의 세부 분류. 다시 분류될 때까지 남은 기록을 읽으려고 둔다. t2부터는 고르지 않는다.
    FINANCE = "finance"
    LEGAL = "legal"
    AUDIO = "audio"


SUBCATEGORY_PARENT: dict[Subcategory, Category] = {
    Subcategory.FRONTEND: Category.DEVELOPMENT,
    Subcategory.BACKEND: Category.DEVELOPMENT,
    Subcategory.MOBILE: Category.DEVELOPMENT,
    Subcategory.GIT: Category.DEVELOPMENT,
    Subcategory.CODE_QUALITY: Category.DEVELOPMENT,
    Subcategory.DEBUGGING: Category.DEVELOPMENT,
    Subcategory.DEV_TOOLS: Category.DEVELOPMENT,
    Subcategory.GAME_DEV: Category.DEVELOPMENT,
    Subcategory.WEB3: Category.DEVELOPMENT,
    Subcategory.TEST_WRITING: Category.TESTING,
    Subcategory.BROWSER_TESTING: Category.TESTING,
    Subcategory.QA: Category.TESTING,
    Subcategory.DEPLOYMENT: Category.DEVOPS,
    Subcategory.INFRASTRUCTURE: Category.DEVOPS,
    Subcategory.MONITORING: Category.DEVOPS,
    Subcategory.RELEASE: Category.DEVOPS,
    Subcategory.DATA_ANALYSIS: Category.DATA,
    Subcategory.DATABASE: Category.DATA,
    Subcategory.MACHINE_LEARNING: Category.DATA,
    Subcategory.VISUALIZATION: Category.DATA,
    Subcategory.PDF: Category.DOCUMENTS,
    Subcategory.OFFICE: Category.DOCUMENTS,
    Subcategory.PRESENTATION: Category.DOCUMENTS,
    Subcategory.DIAGRAM: Category.DOCUMENTS,
    Subcategory.UI_UX: Category.DESIGN,
    Subcategory.VISUAL_DESIGN: Category.DESIGN,
    Subcategory.IMAGE: Category.DESIGN,
    Subcategory.VIDEO: Category.DESIGN,
    Subcategory.ACCESSIBILITY: Category.DESIGN,
    Subcategory.DRAFTING: Category.WRITING,
    Subcategory.TRANSLATION: Category.WRITING,
    Subcategory.EDITING: Category.WRITING,
    Subcategory.SEO: Category.MARKETING,
    Subcategory.SOCIAL_MEDIA: Category.MARKETING,
    Subcategory.ADVERTISING: Category.MARKETING,
    Subcategory.SALES: Category.MARKETING,
    Subcategory.ECOMMERCE: Category.MARKETING,
    Subcategory.COMMUNICATION: Category.PRODUCTIVITY,
    Subcategory.NOTES_CALENDAR: Category.PRODUCTIVITY,
    Subcategory.PROJECT_MANAGEMENT: Category.PRODUCTIVITY,
    Subcategory.AUTOMATION: Category.PRODUCTIVITY,
    Subcategory.LEARNING: Category.PRODUCTIVITY,
    Subcategory.WEB_RESEARCH: Category.RESEARCH,
    Subcategory.ACADEMIC: Category.RESEARCH,
    Subcategory.MARKET_RESEARCH: Category.RESEARCH,
    Subcategory.SECURITY_REVIEW: Category.SECURITY,
    Subcategory.VULNERABILITY: Category.SECURITY,
    Subcategory.AUTH: Category.SECURITY,
    Subcategory.SKILL_AUTHORING: Category.AI_AGENTS,
    Subcategory.MCP: Category.AI_AGENTS,
    Subcategory.AGENT_OPERATIONS: Category.AI_AGENTS,
    Subcategory.AI_ENGINEERING: Category.AI_AGENTS,
    Subcategory.PERSONA: Category.AI_AGENTS,
    Subcategory.INVESTING: Category.FINANCE,
    Subcategory.FINANCIAL_ANALYSIS: Category.FINANCE,
    Subcategory.ACCOUNTING_TAX: Category.FINANCE,
    Subcategory.SPEECH: Category.AUDIO,
    Subcategory.MUSIC: Category.AUDIO,
    Subcategory.SOUND: Category.AUDIO,
    Subcategory.CONTRACTS: Category.LEGAL,
    Subcategory.COMPLIANCE: Category.LEGAL,
    Subcategory.LEGAL_WORK: Category.LEGAL,
    Subcategory.HEALTH: Category.HEALTH_LIFESTYLE,
    Subcategory.LIFESTYLE: Category.HEALTH_LIFESTYLE,
    Subcategory.BUSINESS_OPS: Category.OTHER,
    Subcategory.MISC: Category.OTHER,
    # 예전 기록도 다시 분류되기 전부터 새 카테고리에 보이도록 옮겨 둔다.
    Subcategory.FINANCE: Category.FINANCE,
    Subcategory.LEGAL: Category.LEGAL,
    Subcategory.AUDIO: Category.AUDIO,
}

LEGACY_SUBCATEGORIES = frozenset({Subcategory.FINANCE, Subcategory.LEGAL, Subcategory.AUDIO})
"""t2부터 고르지 않는 세부 분류. 사이트의 세부 분류 목록에도 싣지 않는다."""


class ContentExclusion(StrEnum):
    """분류하면서 사이트에서 빼기로 판단한 이유 (ADR-0020)."""

    # 본문이 없다. 다른 곳으로 옮겨졌다는 안내, 암호화되어 읽을 수 없는 파일 등.
    PLACEHOLDER = "placeholder"
    # 기능을 보여 주려고 만든 견본이라 그 자체로 쓸 일이 없다.
    DEMO = "demo"
    # 한국이 아닌 한 나라의 법률, 세금, 행정이나 그 나라 사람만 쓰는 서비스에 맞춘 스킬 (ADR-0021).
    FOREIGN_REGION = "foreign_region"


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
    # 본문이 중국어·일본어 위주다. 한국 사용자가 원문을 확인할 수 없다 (ADR-0017).
    FOREIGN_LANGUAGE = "foreign_language"


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
    # v6부터 채운다. 이전 프롬프트의 기록에는 없다.
    subcategory: Subcategory | None = None
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
    classify_calls: int = 0

    def roll_over(self, today: date) -> None:
        """날짜가 바뀌면 하루 호출 수를 0부터 다시 센다."""
        if self.day != today:
            self.day = today
            self.summary_calls = 0
            self.classify_calls = 0


class ClassificationRecord(BaseModel):
    """요약과 따로 정한 세부 분류. 어떤 요약과 분류 기준으로 정했는지 남겨 다시 정할지 판단한다."""

    model_config = ConfigDict(frozen=True)

    subcategory: Subcategory
    taxonomy_version: str
    skill_md_hash: GitBlobSha
    summary_prompt_version: str
    model: str
    excluded: ContentExclusion | None = None


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
    classifications: dict[str, ClassificationRecord] = {}
    # 저장소 키마다 날짜별 스타. 급상승 계산에 쓰고 35일만 보관한다 (ADR-0022).
    star_history: dict[str, dict[date, int]] = {}
