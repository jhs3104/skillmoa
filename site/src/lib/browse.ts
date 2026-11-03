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
  page: number;
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
  page: 1,
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
    page: parsePage(params.get('page')),
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
  if (state.page > 1) params.set('page', String(state.page));
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
export function isFirstPage(state: BrowseState, defaultSort: SortKey): boolean {
  return (
    !state.query &&
    !state.category &&
    !state.unflaggedOnly &&
    !state.noAccountOnly &&
    state.sort === defaultSort &&
    state.page === 1
  );
}

export function visibleItems(items: BrowseItem[], state: BrowseState): BrowseItem[] {
  return items.filter((item) => matches(item, state)).sort((a, b) => compare(a, b, state.sort));
}

export const PAGE_SIZE = 50;

function parsePage(value: string | null): number {
  const page = Number(value);
  return Number.isInteger(page) && page > 1 ? page : 1;
}

export function pageCount(total: number): number {
  return Math.max(1, Math.ceil(total / PAGE_SIZE));
}

/** 범위를 벗어난 쪽 번호는 마지막 쪽으로 맞춘다. 결과가 줄어든 뒤 돌아온 링크도 빈 화면이 되지 않는다. */
export function pageSlice<T>(items: T[], page: number): { shown: T[]; page: number; pages: number } {
  const pages = pageCount(items.length);
  const current = Math.min(Math.max(page, 1), pages);
  return { shown: items.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE), page: current, pages };
}

export type PageLink = number | 'gap';

/** 처음, 끝, 현재 주변만 보여 준다. 칸 수가 늘 같아서 쪽을 옮겨도 버튼 위치가 흔들리지 않는다. */
export function pageLinks(page: number, pages: number): PageLink[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1);
  const start = Math.max(2, Math.min(page - 1, pages - 4));
  const end = Math.min(pages - 1, Math.max(page + 1, 5));
  const links: PageLink[] = [1];
  if (start > 2) links.push('gap');
  for (let number = start; number <= end; number += 1) links.push(number);
  if (end < pages - 1) links.push('gap');
  links.push(pages);
  return links;
}

/** 서버와 브라우저가 같은 쪽 번호 마크업을 쓰도록 문자열로 만든다. */
export function pagerHtml(page: number, pages: number, href: (page: number) => string): string {
  if (pages <= 1) return '';
  const step = (target: number, label: string, rel: string): string =>
    target < 1 || target > pages
      ? `<span class="pager__step" aria-disabled="true">${label}</span>`
      : `<a class="pager__step" href="${href(target)}" data-page="${target}" rel="${rel}">${label}</a>`;
  const numbers = pageLinks(page, pages)
    .map((link) =>
      link === 'gap'
        ? '<li class="pager__gap" aria-hidden="true">…</li>'
        : `<li><a class="pager__page" href="${href(link)}" data-page="${link}"${
            link === page ? ' aria-current="page"' : ''
          } aria-label="${link}쪽">${link}</a></li>`,
    )
    .join('');
  return `${step(page - 1, '이전', 'prev')}<ol class="pager__pages">${numbers}</ol><span class="pager__status">${page} / ${pages}</span>${step(page + 1, '다음', 'next')}`;
}

/** 상세에서 돌아오면 보던 위치로 되돌린다. */
export function restoreScroll(saved: unknown): number {
  return typeof saved === 'number' && Number.isFinite(saved) && saved > 0 ? saved : 0;
}
