import production from '../data/skills.json';
import sample from '../data/skills.sample.json';
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

export function sourceUrl(skill: Skill): string {
  const encoded = skill.path.split('/').map(encodeURIComponent).join('/');
  return `https://github.com/${skill.repository}/blob/${encodeURIComponent(skill.defaultBranch)}/${encoded}`;
}

export function repositoryUrl(skill: Skill): string {
  return `https://github.com/${skill.repository}`;
}
