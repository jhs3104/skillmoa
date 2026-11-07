import type { CatalogEntry, KeyValueStore, Recommender, Suggestion } from './types';

export const MIN_QUESTION_CHARS = 2;
export const MAX_QUESTION_CHARS = 200;
export const MAX_SUGGESTIONS = 5;
export const MAX_REASON_CHARS = 160;
export const DAILY_LIMIT_PER_IP = 5;

/**
 * Claude 호출 1회에 KV 쓰기가 3번(IP 카운터, 전체 카운터, 캐시) 일어난다.
 * 무료 한도 1,000회/일을 넘지 않도록 전체 호출을 300회로 제한한다.
 */
export const DAILY_LIMIT_TOTAL = 300;

const CLIENT_COUNTER_TTL_SECONDS = 2 * 86_400;
/** 전체 호출 수는 개인 정보가 아니라 이용 추이를 보려고 오래 남긴다. 쓰기 횟수는 늘지 않는다. */
const TOTAL_COUNTER_TTL_SECONDS = 90 * 86_400;
const CACHE_TTL_SECONDS = 7 * 86_400;

export type Answer =
  | { status: 'ok'; suggestions: Suggestion[]; cached: boolean }
  | { status: 'ip_limited' }
  | { status: 'budget_exhausted' };

export interface Dependencies {
  recommender: Recommender;
  store: KeyValueStore;
  catalog: CatalogEntry[];
  today: string;
}

export function normalizeQuestion(question: string): string {
  return question
    .normalize('NFKC')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/^[\s.,!?~…]+|[\s.,!?~…]+$/g, '');
}

export function isValidQuestion(normalized: string): boolean {
  return normalized.length >= MIN_QUESTION_CHARS && normalized.length <= MAX_QUESTION_CHARS;
}

export async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

/** 캐시 적중은 Claude를 부르지 않으므로 호출 한도를 쓰지 않는다. */
export async function answerQuestion(
  question: string,
  clientAddress: string,
  { recommender, store, catalog, today }: Dependencies,
): Promise<Answer> {
  const normalized = normalizeQuestion(question);
  const cacheKey = `cache:${await sha256(normalized)}`;
  const cached = await store.get(cacheKey);
  if (cached) {
    return { status: 'ok', suggestions: JSON.parse(cached) as Suggestion[], cached: true };
  }

  const clientKey = `ip:${today}:${await sha256(`${today}:${clientAddress}`)}`;
  const totalKey = `total:${today}`;
  const clientCalls = Number((await store.get(clientKey)) ?? 0);
  if (clientCalls >= DAILY_LIMIT_PER_IP) return { status: 'ip_limited' };
  const totalCalls = Number((await store.get(totalKey)) ?? 0);
  if (totalCalls >= DAILY_LIMIT_TOTAL) return { status: 'budget_exhausted' };

  await store.put(clientKey, String(clientCalls + 1), { expirationTtl: CLIENT_COUNTER_TTL_SECONDS });
  await store.put(totalKey, String(totalCalls + 1), { expirationTtl: TOTAL_COUNTER_TTL_SECONDS });

  const suggestions = sanitize(await recommender.recommend(normalized, catalog), catalog);
  if (suggestions.length > 0) {
    await store.put(cacheKey, JSON.stringify(suggestions), { expirationTtl: CACHE_TTL_SECONDS });
  }
  return { status: 'ok', suggestions, cached: false };
}

/** 모델이 지어낸 스킬은 버린다. 링크가 깨지지 않도록 목록에 있는 슬러그만 남긴다. */
function sanitize(suggestions: Suggestion[], catalog: CatalogEntry[]): Suggestion[] {
  const known = new Set(catalog.map(({ slug }) => slug));
  const seen = new Set<string>();
  const clean: Suggestion[] = [];
  for (const { slug, reason } of suggestions) {
    if (!known.has(slug) || seen.has(slug)) continue;
    seen.add(slug);
    clean.push({ slug, reason: reason.trim().slice(0, MAX_REASON_CHARS) });
  }
  return clean.slice(0, MAX_SUGGESTIONS);
}
