import type { APIRoute } from 'astro';
import { skills } from '../lib/data';
import type { CatalogItem } from '../lib/catalog';

/** 맞춤 추천이 브라우저와 Worker에서 함께 읽는 가벼운 목록. */
export const GET: APIRoute = () => {
  const items: CatalogItem[] = skills.map((skill) => ({
    slug: skill.slug,
    name: skill.name,
    summary: skill.summary,
    useWhen: skill.useWhen,
    category: skill.category,
    roles: skill.tags.roles,
    difficulty: skill.tags.difficulty,
    rank: skill.rank,
  }));
  return new Response(JSON.stringify(items), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
};
