import { describe, expect, it } from 'vitest';
import {
  activeFilterCount,
  DEFAULT_STATE,
  PAGE_SIZE,
  isFirstPage,
  pageLinks,
  pagerHtml,
  pageSlice,
  parseState,
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
  subcategory: null,
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

  it('narrows a category to one subcategory', () => {
    const items = [item('pg', { category: 'data', subcategory: 'database' }), item('chart', { category: 'data', subcategory: 'visualization' })];
    const found = visibleItems(items, { ...DEFAULT_STATE, category: 'data', subcategory: 'database' });
    expect(found.map(({ id }) => id)).toEqual(['pg']);
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
    const state = {
      query: 'pdf', category: 'data', subcategory: 'database', sort: 'new',
      unflaggedOnly: true, noAccountOnly: true, view: 'cards', page: 3,
    } as const;
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

  it('keeps a subcategory only under its own category', () => {
    expect(parseState(new URLSearchParams('category=data&sub=database'), ['data']).subcategory).toBe('database');
    expect(parseState(new URLSearchParams('category=data&sub=pdf'), ['data']).subcategory).toBe('');
    expect(parseState(new URLSearchParams('sub=database'), ['data']).subcategory).toBe('');
  });

  it('ignores unknown values', () => {
    const state = parseState(new URLSearchParams('category=nope&sort=hax&view=x&page=-2'), ['data']);
    expect(state).toEqual(DEFAULT_STATE);
  });
});

describe('paging', () => {
  const items = Array.from({ length: 120 }, (_, index) => item(String(index)));

  it('shows one page of rows', () => {
    const { shown, pages } = pageSlice(items, 2);
    expect(shown.map(({ id }) => id)[0]).toBe('50');
    expect(shown).toHaveLength(PAGE_SIZE);
    expect(pages).toBe(3);
  });

  it('moves an out-of-range page to the last one', () => {
    expect(pageSlice(items, 9).page).toBe(3);
    expect(pageSlice([], 4)).toEqual({ shown: [], page: 1, pages: 1 });
  });

  it('keeps the same number of page slots wherever you are', () => {
    expect(pageLinks(1, 20)).toEqual([1, 2, 3, 4, 5, 'gap', 20]);
    expect(pageLinks(10, 20)).toEqual([1, 'gap', 9, 10, 11, 'gap', 20]);
    expect(pageLinks(20, 20)).toEqual([1, 'gap', 16, 17, 18, 19, 20]);
    expect(pageLinks(2, 4)).toEqual([1, 2, 3, 4]);
  });

  it('marks the current page and disables the missing step', () => {
    const html = pagerHtml(1, 3, (page) => `?page=${page}`);
    expect(html).toContain('aria-current="page" aria-label="1쪽"');
    expect(html).toContain('<span class="pager__step" aria-disabled="true">이전</span>');
    expect(html).toContain('href="?page=2" data-page="2" rel="next"');
    expect(pagerHtml(1, 1, String)).toBe('');
  });
});

describe('catalog rows', () => {
  it('builds searchable text and flags from a catalog item', () => {
    const found = toBrowseItem({
      slug: 'a', rank: 3, name: 'PDF Kit', repository: 'acme/kit', summary: '문서를 다룹니다', useWhen: '보고서',
      category: 'documents', subcategory: 'pdf', roles: ['general'], useCases: ['서명'], difficulty: 'beginner', stars: 9,
      pushedAt: '2026-01-02', firstSeenAt: '2026-01-01', runsExternalCode: true, accessesNetwork: false,
      requiresExternalAccount: true, scriptFiles: 'present', installBlocked: false,
    });
    expect(found.text).toContain('pdf kit');
    expect(found.text).toContain('서명');
    expect(found.text).toContain('문서');
    expect(found.noFlags).toBe(false);
    expect(found.noAccount).toBe(false);
  });

  it('keeps server rows only for the untouched first page', () => {
    expect(isFirstPage(DEFAULT_STATE, 'rank')).toBe(true);
    expect(isFirstPage({ ...DEFAULT_STATE, view: 'cards' }, 'rank')).toBe(true);
    expect(isFirstPage({ ...DEFAULT_STATE, query: 'pdf' }, 'rank')).toBe(false);
    expect(isFirstPage({ ...DEFAULT_STATE, noAccountOnly: true }, 'rank')).toBe(false);
    expect(isFirstPage({ ...DEFAULT_STATE, page: 2 }, 'rank')).toBe(false);
    expect(isFirstPage({ ...DEFAULT_STATE, sort: 'new' }, 'new')).toBe(true);
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
