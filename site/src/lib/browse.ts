import type { Category } from './types';

export type SortKey = 'stars' | 'updated' | 'new';
export type ViewKey = 'cards' | 'table';

export interface BrowseItem {
  id: string;
  text: string;
  category: Category;
  rank: number;
  pushedAt: string;
  firstSeenAt: string;
  runsNothing: boolean;
}

export interface BrowseState {
  query: string;
  category: Category | '';
  sort: SortKey;
  localOnly: boolean;
  view: ViewKey;
}

export const DEFAULT_STATE: BrowseState = {
  query: '',
  category: '',
  sort: 'stars',
  localOnly: false,
  view: 'cards',
};

const SORTS: SortKey[] = ['stars', 'updated', 'new'];

export function parseState(params: URLSearchParams, categories: readonly string[]): BrowseState {
  const sort = params.get('sort') as SortKey;
  const category = params.get('category') ?? '';
  return {
    query: params.get('q')?.slice(0, 100) ?? '',
    category: categories.includes(category) ? (category as Category) : '',
    sort: SORTS.includes(sort) ? sort : DEFAULT_STATE.sort,
    localOnly: params.get('local') === '1',
    view: params.get('view') === 'table' ? 'table' : 'cards',
  };
}

export function serializeState(state: BrowseState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.query) params.set('q', state.query);
  if (state.category) params.set('category', state.category);
  if (state.sort !== DEFAULT_STATE.sort) params.set('sort', state.sort);
  if (state.localOnly) params.set('local', '1');
  if (state.view !== DEFAULT_STATE.view) params.set('view', state.view);
  return params;
}

export function matches(item: BrowseItem, state: BrowseState): boolean {
  if (state.category && item.category !== state.category) return false;
  if (state.localOnly && !item.runsNothing) return false;
  const terms = state.query.toLowerCase().split(/\s+/).filter(Boolean);
  return terms.every((term) => item.text.includes(term));
}

export function compare(a: BrowseItem, b: BrowseItem, sort: SortKey): number {
  if (sort === 'updated') {
    return b.pushedAt.localeCompare(a.pushedAt) || a.rank - b.rank;
  }
  if (sort === 'new') {
    return b.firstSeenAt.localeCompare(a.firstSeenAt) || a.rank - b.rank;
  }
  return a.rank - b.rank;
}

export function visibleItems(items: BrowseItem[], state: BrowseState): BrowseItem[] {
  return items.filter((item) => matches(item, state)).sort((a, b) => compare(a, b, state.sort));
}
