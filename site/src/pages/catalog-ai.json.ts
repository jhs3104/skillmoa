import type { APIRoute } from 'astro';
import { jsonFile } from '../lib/catalog';
import { skills } from '../lib/data';

const MAX_CATALOG_ENTRIES = 300;

function firstSentence(text: string): string {
  return text.match(/^.+?[.!?](?=\s|$)/)?.[0] ?? text;
}

/** AI 찾기가 Worker에서 읽는다. 무료 플랜의 CPU 제한 때문에 전체 목록과 분리해 작게 유지한다. */
export const GET: APIRoute = () =>
  jsonFile(
    skills.slice(0, MAX_CATALOG_ENTRIES).map(({ slug, name, summary }) => ({
      slug,
      name,
      summary: firstSentence(summary),
    })),
  );
