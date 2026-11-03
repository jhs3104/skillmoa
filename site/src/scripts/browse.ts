import {
  activeFilterCount,
  DEFAULT_STATE,
  isFirstPage,
  pagerHtml,
  pageCount,
  pageSlice,
  parseState,
  restoreScroll,
  serializeState,
  toBrowseItem,
  visibleItems,
  type BrowseItem,
  type BrowseState,
  type SortKey,
  type ViewKey,
} from '../lib/browse';
import type { CatalogItem } from '../lib/catalog';
import { skillRowHtml, type RowOptions } from '../lib/skill-row';
import type { Category, Subcategory } from '../lib/types';
import { loadCatalog } from './catalog';

const WIDE_SCREEN = '(min-width: 900px)';

interface SavedView {
  scrollY?: unknown;
}

function start(root: HTMLElement): void {
  const list = root.querySelector<HTMLElement>('[data-list]')!;
  const count = root.querySelector<HTMLElement>('[data-count]')!;
  const empty = root.querySelector<HTMLElement>('[data-empty]')!;
  const search = root.querySelector<HTMLInputElement>('input[name="q"]')!;
  const sort = root.querySelector<HTMLSelectElement>('select[name="sort"]')!;
  const categoryInputs = [...root.querySelectorAll<HTMLInputElement>('input[name="category"]')];
  const subGroups = [...root.querySelectorAll<HTMLFieldSetElement>('[data-sub-for]')];
  const local = root.querySelector<HTMLInputElement>('input[name="local"]')!;
  const noAccount = root.querySelector<HTMLInputElement>('input[name="no-account"]')!;
  const filters = root.querySelector<HTMLDialogElement>('[data-filters]')!;
  const filterOpen = root.querySelector<HTMLButtonElement>('[data-filters-open]')!;
  const apply = root.querySelector<HTMLButtonElement>('[data-filters-apply]')!;
  const controls = root.querySelector<HTMLElement>('[data-filter-controls]')!;
  const sheetSlot = root.querySelector<HTMLElement>('[data-sheet-slot]')!;
  const resets = [...root.querySelectorAll<HTMLButtonElement>('[data-reset]')];
  const pager = root.querySelector<HTMLElement>('[data-pager]')!;
  const loadError = root.querySelector<HTMLElement>('[data-load-error]')!;
  const retry = root.querySelector<HTMLButtonElement>('[data-retry]')!;
  const viewButtons = [...root.querySelectorAll<HTMLButtonElement>('[data-view]:not(ol)')];
  const categories = (root.dataset.categories ?? '').split(',').filter(Boolean);
  const defaultSort = (root.dataset.defaultSort ?? DEFAULT_STATE.sort) as SortKey;
  const catalogUrl = root.dataset.catalog!;
  const total = Number(root.dataset.total);
  const rowOptions: RowOptions = { dateKind: root.dataset.dateKind as RowOptions['dateKind'] };

  const saved = (history.state ?? {}) as SavedView;
  const state: BrowseState = parseState(new URLSearchParams(location.search), categories, defaultSort);
  let pendingScroll = restoreScroll(saved.scrollY);
  let catalog: { items: BrowseItem[]; byId: Map<string, CatalogItem> } | null = null;
  let waiting = false;

  history.scrollRestoration = 'manual';

  function syncChrome(): void {
    list.dataset.view = state.view;
    for (const button of viewButtons) {
      button.setAttribute('aria-pressed', String(button.dataset.view === state.view));
    }
    const active = activeFilterCount(state);
    filterOpen.textContent = active > 0 ? `필터 ${active}` : '필터';
    for (const reset of resets) reset.hidden = active === 0 && !state.query;
    history.replaceState(history.state, '', currentUrl());
  }

  function urlFor(page: number): string {
    const query = serializeState({ ...state, page }, defaultSort).toString();
    return query ? `?${query}` : location.pathname;
  }

  function currentUrl(): string {
    return urlFor(state.page);
  }

  function showCount(visible: number): void {
    count.textContent = `${visible}개 스킬`;
    apply.textContent = `${visible}개 스킬 보기`;
    pager.innerHTML = pagerHtml(state.page, pageCount(visible), urlFor);
  }

  function renderRows(): void {
    const visible = visibleItems(catalog!.items, state);
    const { shown, page } = pageSlice(visible, state.page);
    if (page !== state.page) {
      state.page = page;
      history.replaceState(history.state, '', currentUrl());
    }
    list.querySelectorAll('.skill').forEach((row) => row.remove());
    const html = shown.map(({ id }) => skillRowHtml(catalog!.byId.get(id)!, rowOptions)).join('');
    list.insertAdjacentHTML('beforeend', html);
    list.hidden = visible.length === 0;
    empty.hidden = visible.length > 0;
    showCount(visible.length);
  }

  function finishRestore(): void {
    if (pendingScroll) window.scrollTo(0, pendingScroll);
    pendingScroll = 0;
  }

  async function ensureCatalog(): Promise<void> {
    const rows = await loadCatalog(catalogUrl);
    catalog ??= {
      items: rows.map(toBrowseItem),
      byId: new Map(rows.map((row) => [row.slug, row])),
    };
  }

  function render(): void {
    syncChrome();
    if (catalog) {
      renderRows();
      finishRestore();
      return;
    }
    if (isFirstPage(state, defaultSort)) {
      showCount(total);
      finishRestore();
      return;
    }
    if (waiting) return;
    waiting = true;
    count.textContent = '목록을 불러오는 중…';
    loadError.hidden = true;
    ensureCatalog()
      .then(() => {
        waiting = false;
        render();
      })
      .catch(() => {
        waiting = false;
        count.textContent = `${total}개 스킬`;
        loadError.hidden = false;
      });
  }

  /** 조건이 바뀌면 결과가 달라지므로 첫 쪽부터 다시 보여 준다. */
  function renderFromStart(): void {
    state.page = 1;
    render();
  }

  /** 쪽을 옮기면 기록을 남겨 뒤로 가기로 이전 쪽에 돌아갈 수 있게 한다. */
  function goToPage(page: number): void {
    state.page = page;
    history.pushState({}, '', currentUrl());
    render();
    if (!catalog) return;
    const top = root.querySelector<HTMLElement>('.browse__main')!;
    if (top.getBoundingClientRect().top < 0) top.scrollIntoView({ block: 'start' });
    list.querySelector<HTMLAnchorElement>('.skill a')?.focus({ preventScroll: true });
  }

  if (![...sort.options].some(({ value }) => value === state.sort)) state.sort = defaultSort;

  function syncControls(): void {
    search.value = state.query;
    local.checked = state.unflaggedOnly;
    noAccount.checked = state.noAccountOnly;
    sort.value = state.sort;
    for (const input of categoryInputs) input.checked = input.value === state.category;
    for (const group of subGroups) {
      const active = group.dataset.subFor === state.category;
      group.hidden = !active;
      for (const input of group.querySelectorAll<HTMLInputElement>('input')) {
        input.checked = input.value === (active ? state.subcategory : '');
      }
    }
  }

  syncControls();

  search.addEventListener('focus', () => void ensureCatalog().catch(() => undefined), { once: true });
  search.addEventListener('input', () => {
    state.query = search.value;
    renderFromStart();
  });
  sort.addEventListener('change', () => {
    state.sort = sort.value as SortKey;
    renderFromStart();
  });
  local.addEventListener('change', () => {
    state.unflaggedOnly = local.checked;
    renderFromStart();
  });
  noAccount.addEventListener('change', () => {
    state.noAccountOnly = noAccount.checked;
    renderFromStart();
  });
  for (const input of categoryInputs) {
    input.addEventListener('change', () => {
      state.category = input.value as Category | '';
      state.subcategory = '';
      syncControls();
      renderFromStart();
    });
  }
  for (const group of subGroups) {
    group.addEventListener('change', (event) => {
      state.subcategory = (event.target as HTMLInputElement).value as Subcategory | '';
      renderFromStart();
    });
  }
  for (const reset of resets) {
    reset.addEventListener('click', () => {
      state.query = '';
      state.category = '';
      state.subcategory = '';
      state.unflaggedOnly = false;
      state.noAccountOnly = false;
      syncControls();
      renderFromStart();
      (filters.open ? apply : search).focus();
    });
  }
  pager.addEventListener('click', (event) => {
    const link = (event.target as Element).closest<HTMLAnchorElement>('a[data-page]');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    const page = Number(link.dataset.page);
    void ensureCatalog()
      .then(() => goToPage(page))
      .catch(() => {
        loadError.hidden = false;
      });
  });
  window.addEventListener('popstate', () => {
    Object.assign(state, parseState(new URLSearchParams(location.search), categories, defaultSort));
    if (![...sort.options].some(({ value }) => value === state.sort)) state.sort = defaultSort;
    pendingScroll = restoreScroll((history.state as SavedView | null)?.scrollY);
    syncControls();
    render();
  });
  retry.addEventListener('click', () => {
    loadError.hidden = true;
    render();
  });
  for (const button of viewButtons) {
    button.addEventListener('click', () => {
      state.view = button.dataset.view as ViewKey;
      render();
    });
  }

  filterOpen.addEventListener('click', () => {
    sheetSlot.append(controls);
    filters.showModal();
  });
  filters.addEventListener('close', () => filters.after(controls));
  root.querySelector('[data-filters-close]')!.addEventListener('click', () => filters.close());
  apply.addEventListener('click', () => filters.close());
  filters.addEventListener('click', (event) => {
    if (event.target === filters) filters.close();
  });
  window.matchMedia(WIDE_SCREEN).addEventListener('change', () => filters.close());
  window.addEventListener('pagehide', () => {
    history.replaceState({ scrollY: window.scrollY }, '');
  });

  render();

  const prefersLessData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData;
  if (pageCount(total) > 1 && !prefersLessData) {
    const prefetch = (): void => void ensureCatalog().catch(() => undefined);
    if ('requestIdleCallback' in window) requestIdleCallback(prefetch);
    else setTimeout(prefetch, 2000);
  }
}

const root = document.querySelector<HTMLElement>('[data-browse]');
if (root?.querySelector('.skill')) start(root);
