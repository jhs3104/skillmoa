import { describe, expect, it } from 'vitest';
import {
  activeFilterCount,
  DEFAULT_STATE,
  moreLabel,
  PAGE_SIZE,
  pageItems,
  isFirstPage,
  parseState,
  restoreLimit,
  restoreScroll,
  serializeState,
  toBrowseItem,
  visibleItems,
  type BrowseItem,
} from './browse';

const item = (id: string, fields: Partial<BrowseItem> = {}): BrowseItem => ({
  id,
  text: id,
  category: 'documents',
  rank: 1,
  stars: 10,
  pushedAt: '2026-01-01',
  firstSeenAt: '2026-01-01',
  noFlags: true,
  noAccount: true,
  ...fields,
});

describe('visibleItems', () => {
  it('requires every search term to match', () => {
    const items = [item('a', { text: 'pdf 편집 도구' }), item('b', { text: 'pdf 뷰어' })];
    const found = visibleItems(items, { ...DEFAULT_STATE, query: 'PDF 편집' });
    expect(found.map(({ id }) => id)).toEqual(['a']);
  });

  it('filters by category and local-only', () => {
    const items = [
      item('a', { category: 'data' }),
      item('b', { category: 'data', noFlags: false }),
      item('c'),
    ];
    const found = visibleItems(items, { ...DEFAULT_STATE, category: 'data', unflaggedOnly: true });
    expect(found.map(({ id }) => id)).toEqual(['a']);
  });

  it('can hide skills that need an external account', () => {
    const items = [item('free'), item('paid', { noAccount: false })];
    const found = visibleItems(items, { ...DEFAULT_STATE, noAccountOnly: true });
    expect(found.map(({ id }) => id)).toEqual(['free']);
  });

  it('sorts by rank by default, not raw repository stars', () => {
    const items = [item('b', { rank: 2, stars: 900 }), item('a', { rank: 1, stars: 5 })];
    expect(visibleItems(items, DEFAULT_STATE).map(({ id }) => id)).toEqual(['a', 'b']);
  });

  it('sorts by real repository stars when asked, breaking ties by rank', () => {
    const items = [
      item('low', { rank: 1, stars: 5 }),
      item('second', { rank: 3, stars: 900 }),
      item('first', { rank: 2, stars: 900 }),
    ];
    const found = visibleItems(items, { ...DEFAULT_STATE, sort: 'stars' });
    expect(found.map(({ id }) => id)).toEqual(['first', 'second', 'low']);
  });

  it('breaks date ties by rank', () => {
    const items = [item('b', { rank: 2 }), item('a', { rank: 1 })];
    const found = visibleItems(items, { ...DEFAULT_STATE, sort: 'updated' });
    expect(found.map(({ id }) => id)).toEqual(['a', 'b']);
  });

  it('sorts newest first', () => {
    const items = [item('old'), item('new', { firstSeenAt: '2026-02-01', rank: 9 })];
    const found = visibleItems(items, { ...DEFAULT_STATE, sort: 'new' });
    expect(found[0]?.id).toBe('new');
  });
});

describe('URL state', () => {
  it('round-trips through query parameters', () => {
    const state = { query: 'pdf', category: 'data', sort: 'new', unflaggedOnly: true, noAccountOnly: true, view: 'cards' } as const;
    expect(parseState(serializeState(state), ['data'])).toEqual(state);
  });

  it('omits defaults to keep links short', () => {
    expect(serializeState(DEFAULT_STATE).toString()).toBe('');
  });

  it('uses the page default sort for links and missing values', () => {
    const state = parseState(new URLSearchParams(), [], 'new');
    expect(state.sort).toBe('new');
    expect(serializeState(state, 'new').toString()).toBe('');
    expect(serializeState({ ...state, sort: 'rank' }, 'new').toString()).toBe('sort=rank');
  });

  it('ignores unknown values', () => {
    const state = parseState(new URLSearchParams('category=nope&sort=hax&view=x'), ['data']);
    expect(state).toEqual(DEFAULT_STATE);
  });
});

describe('paging', () => {
  const items = Array.from({ length: 120 }, (_, index) => item(String(index)));

  it('shows one page and counts the rest', () => {
    const { shown, remaining } = pageItems(items, PAGE_SIZE);
    expect(shown).toHaveLength(PAGE_SIZE);
    expect(remaining).toBe(70);
  });

  it('never reports negative remainders', () => {
    expect(pageItems(items.slice(0, 3), PAGE_SIZE).remaining).toBe(0);
  });

  it('names the next step in the button', () => {
    expect(moreLabel(250)).toBe('50개 더 보기 (250개 남음)');
    expect(moreLabel(12)).toBe('12개 더 보기');
  });

  it('restores only a sensible limit from history', () => {
    expect(restoreLimit(150)).toBe(150);
    for (const value of [undefined, null, 'x', -50, 0, 75.5, 10]) {
      expect(restoreLimit(value)).toBe(PAGE_SIZE);
    }
  });
});

describe('catalog rows', () => {
  it('builds searchable text and flags from a catalog item', () => {
    const found = toBrowseItem({
      slug: 'a', rank: 3, name: 'PDF Kit', repository: 'acme/kit', summary: '문서를 다룹니다', useWhen: '보고서',
      category: 'documents', roles: ['general'], useCases: ['서명'], difficulty: 'beginner', stars: 9,
      pushedAt: '2026-01-02', firstSeenAt: '2026-01-01', runsExternalCode: true, accessesNetwork: false,
      requiresExternalAccount: true, installBlocked: false,
    });
    expect(found.text).toContain('pdf kit');
    expect(found.text).toContain('서명');
    expect(found.text).toContain('문서');
    expect(found.noFlags).toBe(false);
    expect(found.noAccount).toBe(false);
  });

  it('keeps server rows only for the untouched first page', () => {
    expect(isFirstPage(DEFAULT_STATE, PAGE_SIZE, 'rank')).toBe(true);
    expect(isFirstPage({ ...DEFAULT_STATE, view: 'cards' }, PAGE_SIZE, 'rank')).toBe(true);
    expect(isFirstPage({ ...DEFAULT_STATE, query: 'pdf' }, PAGE_SIZE, 'rank')).toBe(false);
    expect(isFirstPage({ ...DEFAULT_STATE, noAccountOnly: true }, PAGE_SIZE, 'rank')).toBe(false);
    expect(isFirstPage(DEFAULT_STATE, PAGE_SIZE * 2, 'rank')).toBe(false);
    expect(isFirstPage({ ...DEFAULT_STATE, sort: 'new' }, PAGE_SIZE, 'new')).toBe(true);
  });

  it('restores only a usable scroll position', () => {
    expect(restoreScroll(420)).toBe(420);
    for (const value of [undefined, null, 'x', -1, Number.NaN]) expect(restoreScroll(value)).toBe(0);
  });
});

describe('activeFilterCount', () => {
  it('counts category and the local filter, not the search or sort', () => {
    expect(activeFilterCount({ ...DEFAULT_STATE, query: 'pdf', sort: 'new' })).toBe(0);
    expect(activeFilterCount({ ...DEFAULT_STATE, category: 'data', unflaggedOnly: true })).toBe(2);
    expect(activeFilterCount({ ...DEFAULT_STATE, noAccountOnly: true })).toBe(1);
  });
});
