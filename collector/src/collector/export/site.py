"""수집 상태에서 skills.json을 만든다. 같은 상태면 항상 같은 파일이 나온다."""

from collector.config import ExcludeSettings, RankingSettings
from collector.domain.identity import repository_key, skill_slug
from collector.domain.models import (
    SUBCATEGORY_PARENT,
    Category,
    CollectorState,
    Subcategory,
    SummaryRecord,
)
from collector.domain.ranking import rank_skills, select_catalog
from collector.domain.summary_rules import is_current_classification
from collector.domain.tree import script_presence
from collector.export.schema import SiteData, SiteRepository, SiteSkill, SiteTags

_NO_EXCLUSIONS = ExcludeSettings()


def build_site_data(
    state: CollectorState, ranking: RankingSettings, exclude: ExcludeSettings = _NO_EXCLUSIONS
) -> SiteData:
    """요약이 있는 스킬을 상한까지만 내보낸다. 사이트는 요약 없는 스킬을 다루지 않는다.

    빼기로 한 스킬은 상한을 세기 전에 뺀다. 그래야 다른 스킬의 자리를 차지하지 않는다.
    """
    stars = {record.full_name: record.stars for record in state.repositories.values()}
    ranked = rank_skills(state.skills, stars, ranking.star_decay)
    summarized = [
        item
        for item in ranked
        if _has_current_summary(state, item.key) and not _is_excluded(state, item.key, exclude)
    ]
    selected = set(select_catalog(summarized, ranking.catalog_limit, ranking.per_repository_cap))
    exported = [item for item in summarized if item.key in selected]

    skills: list[SiteSkill] = []
    repositories: dict[str, SiteRepository] = {}
    for rank, item in enumerate(exported, start=1):
        skill = state.skills[item.key]
        record = state.repositories[repository_key(skill.repository)]
        summary_record = state.summaries[item.key]
        summary = summary_record.summary
        category, subcategory = _classification(state, item.key, summary_record)
        repositories[record.full_name] = SiteRepository(
            full_name=record.full_name,
            stars=record.stars,
            pushed_at=record.pushed_at.date(),
            license=record.license,
            default_branch=record.default_branch,
        )
        skills.append(
            SiteSkill(
                slug=skill_slug(skill.repository, skill.path),
                rank=rank,
                name=skill.name,
                repository=skill.repository,
                path=skill.path,
                license=skill.license or record.license,
                first_seen_at=skill.first_seen_at,
                summary=summary.summary_ko,
                use_when=summary.use_when,
                category=category,
                subcategory=subcategory,
                tags=SiteTags(
                    roles=summary.tags.roles,
                    use_cases=summary.tags.use_cases,
                    difficulty=summary.tags.difficulty,
                ),
                runs_external_code=summary.runs_external_code,
                accesses_network=summary.accesses_network,
                requires_external_account=summary.requires_external_account,
                script_files=script_presence(skill.path, skill.bundled_files),
                prompt_version=summary_record.prompt_version,
            )
        )
    return SiteData(
        bootstrapped_on=state.bootstrapped_on,
        repositories=tuple(sorted(repositories.values(), key=lambda repo: repo.full_name.lower())),
        skills=tuple(skills),
    )


def _has_current_summary(state: CollectorState, key: str) -> bool:
    record = state.summaries.get(key)
    return record is not None and record.skill_md_hash == state.skills[key].skill_md_hash


def _is_excluded(state: CollectorState, key: str, exclude: ExcludeSettings) -> bool:
    """사람이 정한 목록이 먼저다. 그다음 지금 요약을 보고 한 분류의 판단을 따른다 (ADR-0020)."""
    if key in exclude.keep:
        return False
    repository = state.skills[key].repository.lower()
    if key in exclude.skills or repository in {name.lower() for name in exclude.repositories}:
        return True
    classification = state.classifications.get(key)
    return (
        is_current_classification(classification, state.summaries[key])
        and classification is not None
        and classification.excluded is not None
    )


def _classification(
    state: CollectorState, key: str, summary_record: SummaryRecord
) -> tuple[Category, Subcategory | None]:
    """따로 정한 분류가 지금 요약 기준이면 그것을, 아니면 요약이 고른 분류를 쓴다."""
    classification = state.classifications.get(key)
    if is_current_classification(classification, summary_record):
        assert classification is not None
        return SUBCATEGORY_PARENT[classification.subcategory], classification.subcategory
    return summary_record.summary.category, summary_record.summary.subcategory
