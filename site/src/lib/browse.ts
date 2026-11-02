import type { CatalogItem } from './catalog';
import { CATEGORY_LABELS } from './labels';
import type { Category } from './types';

export type SortKey = 'rank' | 'stars' | 'updated' | 'new';
export type ViewKey = 'cards' | 'table';

export interface BrowseItem {
  id: string;
  text: string;
  category: Category;
  rank: number;
  stars: number;
  pushedAt: string;
  firstSeenAt: string;
  noFlags: boolean;
  noAccount: boolean;
}

export interface BrowseState {
  query: string;
  category: Category | '';
  sort: SortKey;
  unflaggedOnly: boolean;
  noAccountOnly: boolean;
  view: ViewKey;
}

export const SORT_LABELS: Record<SortKey, string> = {
  rank: '대표순',
  stars: '스타순',
  updated: '업데이트순',
  new: '신규순',
};

export const DEFAULT_STATE: BrowseState = {
  query: '',
  category: '',
  sort: 'rank',
  unflaggedOnly: false,
  noAccountOnly: false,
  view: 'table',
};

const SORTS = Object.keys(SORT_LABELS) as SortKey[];

export function parseState(
  params: URLSearchParams,
  categories: readonly string[],
  defaultSort: SortKey = DEFAULT_STATE.sort,
): BrowseState {
  const sort = params.get('sort') as SortKey;
  const category = params.get('category') ?? '';
  return {
    query: params.get('q')?.slice(0, 100) ?? '',
    category: categories.includes(category) ? (category as Category) : '',
    sort: SORTS.includes(sort) ? sort : defaultSort,
    unflaggedOnly: params.get('local') === '1',
    noAccountOnly: params.get('account') === '0',
    view: params.get('view') === 'cards' ? 'cards' : 'table',
  };
}

export function serializeState(
  state: BrowseState,
  defaultSort: SortKey = DEFAULT_STATE.sort,
): URLSearchParams {
  const params = new URLSearchParams();
  if (state.query) params.set('q', state.query);
  if (state.category) params.set('category', state.category);
  if (state.sort !== defaultSort) params.set('sort', state.sort);
  if (state.unflaggedOnly) params.set('local', '1');
  if (state.noAccountOnly) params.set('account', '0');
  if (state.view !== DEFAULT_STATE.view) params.set('view', state.view);
  return params;
}

export function activeFilterCount(state: BrowseState): number {
  return Number(Boolean(state.category)) + Number(state.unflaggedOnly) + Number(state.noAccountOnly);
}

export function matches(item: BrowseItem, state: BrowseState): boolean {
  if (state.category && item.category !== state.category) return false;
  if (state.unflaggedOnly && !item.noFlags) return false;
  if (state.noAccountOnly && !item.noAccount) return false;
  const terms = state.query.toLowerCase().split(/\s+/).filter(Boolean);
  return terms.every((term) => item.text.includes(term));
}

export function compare(a: BrowseItem, b: BrowseItem, sort: SortKey): number {
  if (sort === 'stars') {
    return b.stars - a.stars || a.rank - b.rank;
  }
  if (sort === 'updated') {
    return b.pushedAt.localeCompare(a.pushedAt) || a.rank - b.rank;
  }
  if (sort === 'new') {
    return b.firstSeenAt.localeCompare(a.firstSeenAt) || a.rank - b.rank;
  }
  return a.rank - b.rank;
}

export function toBrowseItem(item: CatalogItem): BrowseItem {
  return {
    id: item.slug,
    text: [item.name, item.repository, item.summary, item.useWhen, CATEGORY_LABELS[item.category], ...item.useCases]
      .join(' ')
      .toLowerCase(),
    category: item.category,
    rank: item.rank,
    stars: item.stars,
    pushedAt: item.pushedAt,
    firstSeenAt: item.firstSeenAt,
    noFlags: !item.runsExternalCode && !item.accessesNetwork,
    noAccount: !item.requiresExternalAccount,
  };
}

/** 첫 화면의 서버 출력만으로 보여 줄 수 있는 상태인지 판단한다. */
export function isFirstPage(state: BrowseState, limit: number, defaultSort: SortKey): boolean {
  return (
    !state.query &&
    !state.category &&
    !state.unflaggedOnly &&
    !state.noAccountOnly &&
    state.sort === defaultSort &&
    limit === PAGE_SIZE
  );
}

export function visibleItems(items: BrowseItem[], state: BrowseState): BrowseItem[] {
  return items.filter((item) => matches(item, state)).sort((a, b) => compare(a, b, state.sort));
}

export const PAGE_SIZE = 50;

export function pageItems<T>(items: T[], limit: number): { shown: T[]; remaining: number } {
  return { shown: items.slice(0, limit), remaining: Math.max(items.length - limit, 0) };
}

export function moreLabel(remaining: number): string {
  return remaining > PAGE_SIZE
    ? `${PAGE_SIZE}개 더 보기 (${remaining}개 남음)`
    : `${remaining}개 더 보기`;
}

/** 상세에서 돌아와도 펼친 만큼 남도록 history에 보관한 값을 되살린다. */
export function restoreScroll(saved: unknown): number {
  return typeof saved === 'number' && Number.isFinite(saved) && saved > 0 ? saved : 0;
}

export function restoreLimit(saved: unknown): number {
  return typeof saved === 'number' && Number.isInteger(saved) && saved >= PAGE_SIZE ? saved : PAGE_SIZE;
}
