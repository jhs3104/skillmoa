"""수집 상태에서 skills.json을 만든다. 같은 상태면 항상 같은 파일이 나온다."""

from collector.domain.identity import repository_key, skill_slug
from collector.domain.models import CollectorState
from collector.domain.ranking import rank_skills
from collector.export.schema import SiteData, SiteRepository, SiteSkill, SiteTags


def build_site_data(state: CollectorState, star_decay: float) -> SiteData:
    """요약이 있는 스킬만 내보낸다. 사이트는 요약 없는 스킬을 다루지 않는다."""
    stars = {record.full_name: record.stars for record in state.repositories.values()}
    ranked = rank_skills(state.skills, stars, star_decay)
    exported = [item for item in ranked if _has_current_summary(state, item.key)]

    skills: list[SiteSkill] = []
    repositories: dict[str, SiteRepository] = {}
    for rank, item in enumerate(exported, start=1):
        skill = state.skills[item.key]
        record = state.repositories[repository_key(skill.repository)]
        summary_record = state.summaries[item.key]
        summary = summary_record.summary
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
                category=summary.category,
                tags=SiteTags(
                    roles=summary.tags.roles,
                    use_cases=summary.tags.use_cases,
                    difficulty=summary.tags.difficulty,
                ),
                runs_external_code=summary.runs_external_code,
                accesses_network=summary.accesses_network,
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
