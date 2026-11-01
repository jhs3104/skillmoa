import reviewedSlugs from '../data/reviewed-skills.json';
import type { Skill } from './types';

/** 이 기준을 넘거나 사람이 검수한 스킬만 검색엔진에 노출한다. */
export const INDEXABLE_MIN_STARS = 50;

const reviewed = new Set<string>(reviewedSlugs);

export function isIndexable(skill: Pick<Skill, 'stars' | 'slug'>): boolean {
  return skill.stars >= INDEXABLE_MIN_STARS || reviewed.has(skill.slug);
}

export function truncate(text: string, maxLength: number): string {
  return text.length <= maxLength ? text : `${text.slice(0, maxLength - 1).trimEnd()}…`;
}
