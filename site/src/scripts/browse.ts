import {
  activeFilterCount,
  DEFAULT_STATE,
  isFirstPage,
  moreLabel,
  PAGE_SIZE,
  pageItems,
  parseState,
  restoreLimit,
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
import type { Category } from '../lib/types';
import { loadCatalog } from './catalog';

const WIDE_SCREEN = '(min-width: 900px)';

interface SavedView {
  limit?: unknown;
  scrollY?: unknown;
}

function start(root: HTMLElement): void {
  const list = root.querySelector<HTMLElement>('[data-list]')!;
  const count = root.querySelector<HTMLElement>('[data-count]')!;
  const empty = root.querySelector<HTMLElement>('[data-empty]')!;
  const search = root.querySelector<HTMLInputElement>('input[name="q"]')!;
  const sort = root.querySelector<HTMLSelectElement>('select[name="sort"]')!;
  const categoryInputs = [...root.querySelectorAll<HTMLInputElement>('input[name="category"]')];
  const local = root.querySelector<HTMLInputElement>('input[name="local"]')!;
  const noAccount = root.querySelector<HTMLInputElement>('input[name="no-account"]')!;
  const filters = root.querySelector<HTMLDialogElement>('[data-filters]')!;
  const filterOpen = root.querySelector<HTMLButtonElement>('[data-filters-open]')!;
  const apply = root.querySelector<HTMLButtonElement>('[data-filters-apply]')!;
  const controls = root.querySelector<HTMLElement>('[data-filter-controls]')!;
  const sheetSlot = root.querySelector<HTMLElement>('[data-sheet-slot]')!;
  const resets = [...root.querySelectorAll<HTMLButtonElement>('[data-reset]')];
  const more = root.querySelector<HTMLButtonElement>('[data-more]')!;
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
  let limit = restoreLimit(saved.limit);
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
    const query = serializeState(state, defaultSort).toString();
    history.replaceState({ limit }, '', query ? `?${query}` : location.pathname);
  }

  function showCount(visible: number, remaining: number): void {
    count.textContent = `${visible}개 스킬`;
    apply.textContent = `${visible}개 스킬 보기`;
    more.hidden = remaining === 0;
    more.textContent = moreLabel(remaining);
  }

  function renderRows(): void {
    const visible = visibleItems(catalog!.items, state);
    const { shown, remaining } = pageItems(visible, limit);
    list.querySelectorAll('.skill').forEach((row) => row.remove());
    const html = shown.map(({ id }) => skillRowHtml(catalog!.byId.get(id)!, rowOptions)).join('');
    list.insertAdjacentHTML('beforeend', html);
    list.hidden = visible.length === 0;
    empty.hidden = visible.length > 0;
    showCount(visible.length, remaining);
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
    if (isFirstPage(state, limit, defaultSort)) {
      showCount(total, Math.max(total - PAGE_SIZE, 0));
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

  /** 조건이 바뀌면 결과가 달라지므로 첫 묶음부터 다시 보여 준다. */
  function renderFromStart(): void {
    limit = PAGE_SIZE;
    render();
  }

  if (![...sort.options].some(({ value }) => value === state.sort)) state.sort = defaultSort;

  function syncControls(): void {
    search.value = state.query;
    local.checked = state.unflaggedOnly;
    noAccount.checked = state.noAccountOnly;
    sort.value = state.sort;
    for (const input of categoryInputs) input.checked = input.value === state.category;
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
      renderFromStart();
    });
  }
  for (const reset of resets) {
    reset.addEventListener('click', () => {
      state.query = '';
      state.category = '';
      state.unflaggedOnly = false;
      state.noAccountOnly = false;
      syncControls();
      renderFromStart();
      (filters.open ? apply : search).focus();
    });
  }
  more.addEventListener('click', () => {
    limit += PAGE_SIZE;
    const firstNew = list.querySelectorAll('.skill').length;
    void ensureCatalog()
      .then(() => {
        render();
        list.querySelectorAll('.skill')[firstNew]?.querySelector('a')?.focus({ preventScroll: true });
      })
      .catch(() => {
        limit -= PAGE_SIZE;
        loadError.hidden = false;
      });
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
    history.replaceState({ limit, scrollY: window.scrollY }, '');
  });

  render();

  const prefersLessData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData;
  if (total > PAGE_SIZE && !prefersLessData) {
    const prefetch = (): void => void ensureCatalog().catch(() => undefined);
    if ('requestIdleCallback' in window) requestIdleCallback(prefetch);
    else setTimeout(prefetch, 2000);
  }
}

const root = document.querySelector<HTMLElement>('[data-browse]');
if (root?.querySelector('.skill')) start(root);
