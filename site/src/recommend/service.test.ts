import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  answerQuestion,
  DAILY_LIMIT_PER_IP,
  DAILY_LIMIT_TOTAL,
  isValidQuestion,
  normalizeQuestion,
  type Dependencies,
} from './service';
import type { KeyValueStore, Recommender, Suggestion } from './types';

class MemoryStore implements KeyValueStore {
  values = new Map<string, string>();
  writes = 0;

  async get(key: string): Promise<string | null> {
    return this.values.get(key) ?? null;
  }

  async put(key: string, value: string): Promise<void> {
    this.writes += 1;
    this.values.set(key, value);
  }
}

const catalog = [
  { slug: 'pdf', name: 'pdf', summary: 'PDF 처리' },
  { slug: 'docx', name: 'docx', summary: 'Word 처리' },
];

function recommenderReturning(...suggestions: Suggestion[]): Recommender {
  return { recommend: vi.fn().mockResolvedValue(suggestions) };
}

describe('normalizeQuestion', () => {
  it('merges questions that differ only in form', () => {
    expect(normalizeQuestion('  PDF   합치기!! ')).toBe(normalizeQuestion('pdf 합치기'));
  });

  it('normalizes full-width characters', () => {
    expect(normalizeQuestion('ＰＤＦ')).toBe('pdf');
  });
});

describe('isValidQuestion', () => {
  it('rejects empty and oversized questions', () => {
    expect(isValidQuestion('')).toBe(false);
    expect(isValidQuestion('가'.repeat(201))).toBe(false);
    expect(isValidQuestion('PDF 합치기')).toBe(true);
  });
});

describe('answerQuestion', () => {
  let store: MemoryStore;
  let deps: Dependencies;

  beforeEach(() => {
    store = new MemoryStore();
    deps = {
      store,
      catalog,
      today: '2026-11-01',
      recommender: recommenderReturning({ slug: 'pdf', reason: ' 맞습니다 ' }),
    };
  });

  it('returns validated suggestions', async () => {
    const answer = await answerQuestion('pdf 합치기', '1.1.1.1', deps);
    expect(answer).toEqual({
      status: 'ok',
      cached: false,
      suggestions: [{ slug: 'pdf', reason: '맞습니다' }],
    });
  });

  it('drops skills the model invented and duplicates', async () => {
    deps.recommender = recommenderReturning(
      { slug: 'ghost', reason: 'x' },
      { slug: 'pdf', reason: 'a' },
      { slug: 'pdf', reason: 'b' },
    );
    const answer = await answerQuestion('pdf', '1.1.1.1', deps);
    expect(answer).toMatchObject({ suggestions: [{ slug: 'pdf', reason: 'a' }] });
  });

  it('serves equivalent questions from cache without calling Claude', async () => {
    await answerQuestion('PDF 합치기', '1.1.1.1', deps);
    const answer = await answerQuestion(' pdf  합치기? ', '2.2.2.2', deps);
    expect(answer).toMatchObject({ status: 'ok', cached: true });
    expect(deps.recommender.recommend).toHaveBeenCalledTimes(1);
  });

  it('does not count cache hits against the client limit', async () => {
    for (let index = 0; index < DAILY_LIMIT_PER_IP + 3; index += 1) {
      const answer = await answerQuestion('같은 질문', '1.1.1.1', deps);
      expect(answer.status).toBe('ok');
    }
  });

  it('limits calls per client', async () => {
    for (let index = 0; index < DAILY_LIMIT_PER_IP; index += 1) {
      await answerQuestion(`질문 ${index}`, '1.1.1.1', deps);
    }
    expect((await answerQuestion('다른 질문', '1.1.1.1', deps)).status).toBe('ip_limited');
    expect((await answerQuestion('다른 질문', '2.2.2.2', deps)).status).toBe('ok');
  });

  it('stops at the daily budget', async () => {
    store.values.set('total:2026-11-01', String(DAILY_LIMIT_TOTAL));
    expect((await answerQuestion('질문', '1.1.1.1', deps)).status).toBe('budget_exhausted');
    expect(deps.recommender.recommend).not.toHaveBeenCalled();
  });

  it('stays inside the KV free write quota at the daily budget', async () => {
    await answerQuestion('질문', '1.1.1.1', deps);
    expect(store.writes * DAILY_LIMIT_TOTAL).toBeLessThanOrEqual(1000);
  });

  it('does not cache empty answers', async () => {
    deps.recommender = recommenderReturning();
    await answerQuestion('없는 스킬', '1.1.1.1', deps);
    expect([...store.values.keys()].some((key) => key.startsWith('cache:'))).toBe(false);
  });

  it('counts failed calls so outages cannot be used to spend the budget', async () => {
    deps.recommender = { recommend: vi.fn().mockRejectedValue(new Error('down')) };
    await expect(answerQuestion('질문', '1.1.1.1', deps)).rejects.toThrow('down');
    expect(store.values.get('total:2026-11-01')).toBe('1');
  });

  it('does not store raw client addresses', async () => {
    await answerQuestion('질문', '203.0.113.9', deps);
    expect([...store.values.keys()].join()).not.toContain('203.0.113.9');
  });
});
