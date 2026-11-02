import { licenseStatus } from './license';
import type { Category, Difficulty, Role, Skill } from './types';

/** 목록 행을 그리고 검색하는 데 필요한 값만 담는다. 상세 페이지 내용은 넣지 않는다. */
export interface CatalogItem {
  slug: string;
  rank: number;
  name: string;
  repository: string;
  summary: string;
  useWhen: string;
  category: Category;
  roles: Role[];
  useCases: string[];
  difficulty: Difficulty;
  stars: number;
  pushedAt: string;
  firstSeenAt: string;
  runsExternalCode: boolean;
  accessesNetwork: boolean;
  requiresExternalAccount: boolean;
  installBlocked: boolean;
}

export function toCatalogItem(skill: Skill): CatalogItem {
  return {
    slug: skill.slug,
    rank: skill.rank,
    name: skill.name,
    repository: skill.repository,
    summary: skill.summary,
    useWhen: skill.useWhen,
    category: skill.category,
    roles: skill.tags.roles,
    useCases: skill.tags.useCases,
    difficulty: skill.tags.difficulty,
    stars: skill.stars,
    pushedAt: skill.pushedAt,
    firstSeenAt: skill.firstSeenAt,
    runsExternalCode: skill.runsExternalCode,
    accessesNetwork: skill.accessesNetwork,
    requiresExternalAccount: skill.requiresExternalAccount,
    installBlocked: licenseStatus(skill.license) === 'restricted',
  };
}

export function jsonFile(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
