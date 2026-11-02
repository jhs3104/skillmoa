"""저장소 발견과 SKILL.md 스캔. 결과는 전부 CollectorState에 누적된다."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import httpx

from collector.config import Settings
from collector.domain.filters import (
    content_exclusion,
    mark_duplicates,
    path_exclusion,
    repository_exclusion,
)
from collector.domain.frontmatter import parse_skill_document
from collector.domain.identity import repository_key, skill_dir, skill_key
from collector.domain.models import (
    CollectorState,
    ExclusionReason,
    Repository,
    RepositoryRecord,
    SkillRecord,
)
from collector.domain.ranking import rank_skills, select_catalog
from collector.domain.tree import SkillFile, find_skill_files
from collector.pipeline.content import SkillContentStore
from collector.pipeline.metrics import RunMetrics
from collector.sources.code_search import discover_by_size
from collector.sources.curated import parse_marketplace, parse_repository_links
from collector.sources.github import GitHubClient

logger = logging.getLogger(__name__)

CHECKPOINT_EVERY_REPOSITORIES = 20
HEAD_REF = "HEAD"


@dataclass
class Discovered:
    full_name: str
    repository: Repository | None = None
    sources: set[str] = field(default_factory=set)


@dataclass
class CollectContext:
    state: CollectorState
    github: GitHubClient
    content: SkillContentStore
    settings: Settings
    today: date
    metrics: RunMetrics
    checkpoint: Callable[[], None]


def discover(context: CollectContext, *, full_scan: bool, small: bool) -> dict[str, Discovered]:
    """소스별 저장소를 모은다. 같은 저장소가 여러 소스에 있어도 하나로 합친다."""
    found: dict[str, Discovered] = {}
    settings = context.settings.discovery

    def add(full_name: str, source: str, repository: Repository | None = None) -> None:
        entry = found.setdefault(repository_key(full_name), Discovered(full_name))
        entry.sources.add(source)
        entry.repository = repository or entry.repository

    for full_name in settings.seed_repositories:
        add(full_name, "seed")

    if not small:
        for full_name in _curated_repositories(context):
            add(full_name, "curated")

    topics = settings.topics[:1] if small else settings.topics
    pages = 1 if small else settings.search_pages_per_topic
    for topic in topics:
        for repository in context.github.search_repositories(f"topic:{topic}", pages):
            add(repository.full_name, f"topic:{topic}", repository)

    if full_scan and not context.github.authenticated:
        logger.warning("코드 검색은 토큰이 필요해서 건너뜁니다")
    elif full_scan:
        search = context.github.search_code
        for full_name in discover_by_size(search, settings.code_search_max_size):
            add(full_name, "code_search")

    context.metrics.discovered_repositories = len(found)
    return found


def _curated_repositories(context: CollectContext) -> set[str]:
    settings = context.settings.discovery
    github = context.github
    repositories: set[str] = set()
    for host in settings.marketplaces:
        raw = github.fetch_raw(host, HEAD_REF, ".claude-plugin/marketplace.json")
        if raw is not None:
            repositories |= parse_marketplace(raw.decode("utf-8", errors="replace"), host)
    for full_name in settings.awesome_lists:
        raw = github.fetch_raw(full_name, HEAD_REF, "README.md")
        if raw is not None:
            repositories |= parse_repository_links(raw.decode("utf-8", errors="replace"))
    return repositories


def register_repositories(context: CollectContext, found: dict[str, Discovered]) -> None:
    """메타데이터가 없는 항목만 조회한다. 재개할 때는 이미 아는 저장소를 건너뛴다."""
    for key, entry in sorted(found.items()):
        known = context.state.repositories.get(key)
        repository = entry.repository or known
        if repository is None:
            try:
                repository = context.github.get_repository(entry.full_name)
            except httpx.HTTPStatusError as error:
                logger.warning("저장소 조회 실패 %s: %s", entry.full_name, error)
                context.metrics.failed_repositories += 1
                continue
        if repository is not None:
            upsert_repository(context, repository, entry.sources)


def upsert_repository(
    context: CollectContext, repository: Repository, sources: set[str]
) -> RepositoryRecord:
    state = context.state
    key = repository_key(repository.full_name)
    known = state.repositories.get(key)
    exclusion = repository_exclusion(repository)
    record = RepositoryRecord(
        **repository.model_dump(include=set(Repository.model_fields)),
        first_seen_at=known.first_seen_at if known else context.today,
        scanned_pushed_at=known.scanned_pushed_at if known else None,
        exclusion=exclusion,
        sources=tuple(sorted(set(known.sources if known else ()) | sources)),
    )
    state.repositories[key] = record
    return record


def refresh_known_repositories(context: CollectContext) -> None:
    """알려진 저장소의 스타와 pushed_at을 갱신한다. 삭제와 이름 변경도 여기서 처리한다."""
    state = context.state
    for key, record in sorted(state.repositories.items()):
        if record.exclusion is not None:
            continue
        try:
            repository = context.github.get_repository(record.full_name)
        except httpx.HTTPStatusError as error:
            logger.warning("저장소 갱신 실패 %s: %s", record.full_name, error)
            context.metrics.failed_repositories += 1
            continue
        if repository is None:
            _forget_repository(context, key)
            continue
        if repository_key(repository.full_name) != key:
            _rename_repository(context, record, repository.full_name)
        upsert_repository(context, repository, set())
        context.metrics.refreshed_repositories += 1


def _forget_repository(context: CollectContext, key: str) -> None:
    state = context.state
    full_name = state.repositories.pop(key).full_name
    for skill_id, skill in list(state.skills.items()):
        if skill.repository == full_name:
            _remove_skill(context, skill_id)


def _rename_repository(context: CollectContext, record: RepositoryRecord, new_name: str) -> None:
    """이름만 바뀐 저장소의 firstSeenAt과 요약을 잃지 않도록 키를 옮긴다."""
    state = context.state
    owner, _, name = new_name.partition("/")
    state.repositories[repository_key(new_name)] = record.model_copy(
        update={"owner": owner, "name": name}
    )
    del state.repositories[repository_key(record.full_name)]

    for skill_id, skill in list(state.skills.items()):
        if skill.repository != record.full_name:
            continue
        new_id = skill_key(new_name, skill.path)
        del state.skills[skill_id]
        state.skills[new_id] = skill.model_copy(update={"repository": new_name})
        for table in (state.summaries, state.summary_failures):
            if skill_id in table:
                table[new_id] = table.pop(skill_id)


def needs_scan(record: RepositoryRecord) -> bool:
    return record.exclusion is None and record.pushed_at != record.scanned_pushed_at


def scan_repositories(
    context: CollectContext,
    target: int | None,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """스타가 많은 저장소부터 스캔한다. target개를 채우거나 시간 예산을 쓰면 멈춘다."""
    pending = [record for record in context.state.repositories.values() if needs_scan(record)]
    pending.sort(key=lambda record: (-record.stars, record.full_name.lower()))

    if target is not None and _catalog_is_full(context, target):
        return
    deadline = clock() + context.settings.github.max_scan_minutes * 60
    for index, record in enumerate(pending, start=1):
        if index > 1 and clock() >= deadline:
            context.metrics.scan_deferred_repositories = len(pending) - index + 1
            logger.warning("스캔 시간 예산 소진, %d개는 다음 실행으로", len(pending) - index + 1)
            break
        try:
            _scan_repository(context, record)
        except httpx.HTTPStatusError as error:
            logger.warning("스캔 실패 %s: %s", record.full_name, error)
            context.metrics.failed_repositories += 1
            continue
        if index % CHECKPOINT_EVERY_REPOSITORIES == 0:
            context.checkpoint()
        if target is not None and _catalog_is_full(context, target):
            break
    apply_duplicates(context)


def apply_duplicates(context: CollectContext) -> None:
    stars = {record.full_name: record.stars for record in context.state.repositories.values()}
    context.state.skills = mark_duplicates(context.state.skills, stars)


def _catalog_is_full(context: CollectContext, target: int) -> bool:
    apply_duplicates(context)
    return len(catalog_keys(context, target)) >= target


def catalog_keys(context: CollectContext, limit: int) -> list[str]:
    state = context.state
    ranking = context.settings.ranking
    stars = {record.full_name: record.stars for record in state.repositories.values()}
    ranked = rank_skills(state.skills, stars, ranking.star_decay)
    return select_catalog(ranked, limit, ranking.per_repository_cap)


def files_to_read(files: list[SkillFile], per_repository_cap: int) -> list[SkillFile]:
    """목록에 실을 수 있는 수만큼만 읽는다. 스킬 수천 개짜리 저장소가 한도를 다 쓰지 않게 한다."""
    shallow_first = sorted(files, key=lambda file: (file.path.count("/"), file.path))
    return shallow_first[: per_repository_cap * 2]


def _scan_repository(context: CollectContext, record: RepositoryRecord) -> None:
    metrics = context.metrics
    tree = context.github.get_tree(record)
    metrics.scanned_repositories += 1
    if tree is None:
        _mark_scanned(context, record)
        return
    if tree.truncated:
        logger.warning("tree가 잘렸습니다: %s", record.full_name)
        metrics.truncated_trees += 1

    files = find_skill_files(tree.entries)
    complete = True
    cap = context.settings.ranking.per_repository_cap
    for file in files_to_read(files, cap):
        complete = _record_skill(context, record, file) and complete

    if not tree.truncated:
        current = {skill_key(record.full_name, file.path) for file in files}
        for skill_id, skill in list(context.state.skills.items()):
            if skill.repository == record.full_name and skill_id not in current:
                _remove_skill(context, skill_id)
                metrics.removed_skills += 1

    if complete:
        _mark_scanned(context, record)


def _mark_scanned(context: CollectContext, record: RepositoryRecord) -> None:
    key = repository_key(record.full_name)
    context.state.repositories[key] = record.model_copy(
        update={"scanned_pushed_at": record.pushed_at}
    )


def _remove_skill(context: CollectContext, skill_id: str) -> None:
    state = context.state
    state.skills.pop(skill_id, None)
    state.summaries.pop(skill_id, None)
    state.summary_failures.pop(skill_id, None)


def _record_skill(context: CollectContext, record: RepositoryRecord, file: SkillFile) -> bool:
    """스킬 하나를 상태에 반영한다. 본문을 못 받으면 False를 돌려 재스캔을 남긴다."""
    state = context.state
    skill_id = skill_key(record.full_name, file.path)
    known = state.skills.get(skill_id)

    if known is not None and known.skill_md_hash == file.sha:
        state.skills[skill_id] = known.model_copy(
            update={"last_seen_at": context.today, "bundled_files": file.bundled_files}
        )
        return True

    text = context.content.read(record, file.path, file.sha)
    if text is None:
        return False

    document = parse_skill_document(text)
    minimum = context.settings.filter.min_body_chars
    exclusion: ExclusionReason | None = path_exclusion(file.path) or content_exclusion(
        document.body, minimum
    )
    if exclusion is not None:
        context.metrics.excluded[exclusion] += 1

    state.skills[skill_id] = SkillRecord(
        repository=record.full_name,
        path=file.path,
        skill_md_hash=file.sha,
        name=document.name or _fallback_name(record, file.path),
        first_seen_at=known.first_seen_at if known else context.today,
        last_seen_at=context.today,
        license=document.license,
        exclusion=exclusion,
        bundled_files=file.bundled_files,
    )
    if known is None:
        context.metrics.new_skills += 1
    else:
        context.metrics.updated_skills += 1
    return True


def _fallback_name(record: RepositoryRecord, path: str) -> str:
    directory = skill_dir(path)
    return directory.rpartition("/")[2] or record.name
