import type { APIRoute } from 'astro';
import { env } from 'cloudflare:workers';
import { ClaudeRecommender } from '../../recommend/claude';
import {
  answerQuestion,
  isValidQuestion,
  MAX_QUESTION_CHARS,
  normalizeQuestion,
} from '../../recommend/service';
import type { CatalogEntry } from '../../recommend/types';

export const prerender = false;

function json(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}

async function loadCatalog(url: URL): Promise<CatalogEntry[]> {
  const response = await env.ASSETS.fetch(new URL('/catalog-ai.json', url));
  if (!response.ok) throw new Error(`catalog: ${response.status}`);
  return (await response.json()) as CatalogEntry[];
}

export const POST: APIRoute = async ({ request, url }) => {
  const origin = request.headers.get('origin');
  if (origin !== url.origin) return json({ error: 'forbidden' }, 403);

  const body = (await request.json().catch(() => null)) as { question?: unknown } | null;
  const question = typeof body?.question === 'string' ? body.question.slice(0, MAX_QUESTION_CHARS + 1) : '';
  if (!isValidQuestion(normalizeQuestion(question))) {
    return json({ error: 'invalid_question' }, 400);
  }

  const { ANTHROPIC_API_KEY: apiKey, RECOMMEND_KV: store, RECOMMEND_MODEL: model } = env;
  if (!apiKey || !store || !model) return json({ error: 'unavailable' }, 503);

  try {
    const answer = await answerQuestion(question, request.headers.get('cf-connecting-ip') ?? 'unknown', {
      recommender: new ClaudeRecommender({ apiKey, model, baseURL: env.ANTHROPIC_BASE_URL }),
      store,
      catalog: await loadCatalog(url),
      today: new Date().toISOString().slice(0, 10),
    });
    if (answer.status === 'ip_limited') return json({ error: 'rate_limited' }, 429);
    if (answer.status === 'budget_exhausted') return json({ error: 'budget_exhausted' }, 503);
    return json({ suggestions: answer.suggestions, cached: answer.cached });
  } catch (error) {
    console.error('recommend failed', error);
    return json({ error: 'unavailable' }, 503);
  }
};
