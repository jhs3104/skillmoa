import { describe, expect, it } from 'vitest';
import { DEFAULT_STATE, parseState, serializeState, visibleItems, type BrowseItem } from './browse';

const item = (id: string, fields: Partial<BrowseItem> = {}): BrowseItem => ({
  id,
  text: id,
  category: 'documents',
  rank: 1,
  pushedAt: '2026-01-01',
  firstSeenAt: '2026-01-01',
  runsNothing: true,
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
      item('b', { category: 'data', runsNothing: false }),
      item('c'),
    ];
    const found = visibleItems(items, { ...DEFAULT_STATE, category: 'data', localOnly: true });
    expect(found.map(({ id }) => id)).toEqual(['a']);
  });

  it('sorts by rank, not raw repository stars', () => {
    const items = [item('b', { rank: 2 }), item('a', { rank: 1 })];
    expect(visibleItems(items, DEFAULT_STATE).map(({ id }) => id)).toEqual(['a', 'b']);
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
    const state = { query: 'pdf', category: 'data', sort: 'new', localOnly: true, view: 'table' } as const;
    expect(parseState(serializeState(state), ['data'])).toEqual(state);
  });

  it('omits defaults to keep links short', () => {
    expect(serializeState(DEFAULT_STATE).toString()).toBe('');
  });

  it('ignores unknown values', () => {
    const state = parseState(new URLSearchParams('category=nope&sort=hax&view=x'), ['data']);
    expect(state).toEqual(DEFAULT_STATE);
  });
});
