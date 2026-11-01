import type { Skill } from './types';

/** 이 기준을 넘는 스킬만 검색엔진에 노출한다. 얇은 페이지가 사이트 평가를 낮추지 않게 한다. */
export const INDEXABLE_MIN_STARS = 50;

export function isIndexable(skill: Pick<Skill, 'stars'>): boolean {
  return skill.stars >= INDEXABLE_MIN_STARS;
}

export function truncate(text: string, maxLength: number): string {
  return text.length <= maxLength ? text : `${text.slice(0, maxLength - 1).trimEnd()}…`;
}
