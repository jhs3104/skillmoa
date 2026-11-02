import production from '../data/skills.json';
import sample from '../data/skills.sample.json';
import { isNewSkill } from './freshness';
import type { SiteData, Skill } from './types';

/** 샘플 요약은 사람이 쓴 개발용 데이터다. 명시적으로 켠 빌드에서만 쓴다. */
const useSample = import.meta.env.PUBLIC_USE_SAMPLE_DATA === '1';
const data = (useSample ? sample : production) as unknown as SiteData;

export const isSampleData = useSample;
export const bootstrappedOn = data.bootstrappedOn;

const repositories = new Map(data.repositories.map((repository) => [repository.fullName, repository]));

export const skills: Skill[] = data.skills.flatMap((skill) => {
  const repository = repositories.get(skill.repository);
  if (!repository) return [];
  return [{
    ...skill,
    stars: repository.stars,
    pushedAt: repository.pushedAt,
    defaultBranch: repository.defaultBranch,
  }];
});

export function freshSkills(today = new Date().toISOString().slice(0, 10)): Skill[] {
  return skills
    .filter((skill) => isNewSkill(skill.firstSeenAt, today, bootstrappedOn))
    .sort((a, b) => b.firstSeenAt.localeCompare(a.firstSeenAt) || a.rank - b.rank);
}

export function sourceUrl(skill: Skill): string {
  const encoded = skill.path.split('/').map(encodeURIComponent).join('/');
  return `https://github.com/${skill.repository}/blob/${encodeURIComponent(skill.defaultBranch)}/${encoded}`;
}

/** LICENSE 파일이 저장소 루트가 아니라 스킬 폴더에 있는 경우가 있다. */
export function skillFolderUrl(skill: Skill): string {
  const folder = skill.path.split('/').slice(0, -1).map(encodeURIComponent).join('/');
  if (!folder) return repositoryUrl(skill);
  return `https://github.com/${skill.repository}/tree/${encodeURIComponent(skill.defaultBranch)}/${folder}`;
}

export function repositoryUrl(skill: Skill): string {
  return `https://github.com/${skill.repository}`;
}
