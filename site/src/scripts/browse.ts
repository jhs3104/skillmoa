import {
  activeFilterCount,
  DEFAULT_STATE,
  moreLabel,
  PAGE_SIZE,
  pageItems,
  parseState,
  restoreLimit,
  serializeState,
  visibleItems,
  type BrowseItem,
  type BrowseState,
  type SortKey,
  type ViewKey,
} from '../lib/browse';
import type { Category } from '../lib/types';

const WIDE_SCREEN = '(min-width: 900px)';

function start(root: HTMLElement): void {
  const list = root.querySelector<HTMLElement>('[data-list]')!;
  const nodes = [...list.querySelectorAll<HTMLElement>('.skill')];
  const count = root.querySelector<HTMLElement>('[data-count]')!;
  const empty = root.querySelector<HTMLElement>('[data-empty]')!;
  const search = root.querySelector<HTMLInputElement>('input[name="q"]')!;
  const sort = root.querySelector<HTMLSelectElement>('select[name="sort"]')!;
  const categoryInputs = [...root.querySelectorAll<HTMLInputElement>('input[name="category"]')];
  const local = root.querySelector<HTMLInputElement>('input[name="local"]')!;
  const filters = root.querySelector<HTMLDialogElement>('[data-filters]')!;
  const filterOpen = root.querySelector<HTMLButtonElement>('[data-filters-open]')!;
  const apply = root.querySelector<HTMLButtonElement>('[data-filters-apply]')!;
  const controls = root.querySelector<HTMLElement>('[data-filter-controls]')!;
  const sheetSlot = root.querySelector<HTMLElement>('[data-sheet-slot]')!;
  const resets = [...root.querySelectorAll<HTMLButtonElement>('[data-reset]')];
  const more = root.querySelector<HTMLButtonElement>('[data-more]')!;
  const viewButtons = [...root.querySelectorAll<HTMLButtonElement>('[data-view]:not(ol)')];
  const categories = (root.dataset.categories ?? '').split(',').filter(Boolean);
  const defaultSort = (root.dataset.defaultSort ?? DEFAULT_STATE.sort) as SortKey;

  const items: BrowseItem[] = nodes.map((node) => ({
    id: node.dataset.id!,
    text: node.dataset.text!,
    category: node.dataset.category as Category,
    rank: Number(node.dataset.rank),
    stars: Number(node.dataset.stars),
    pushedAt: node.dataset.pushed!,
    firstSeenAt: node.dataset.firstSeen!,
    noFlags: node.dataset.local === '1',
  }));
  const nodeById = new Map(nodes.map((node) => [node.dataset.id!, node]));
  const state: BrowseState = parseState(new URLSearchParams(location.search), categories, defaultSort);
  let limit = restoreLimit((history.state as { limit?: unknown } | null)?.limit);

  function render(): void {
    const visible = visibleItems(items, state);
    const { shown, remaining } = pageItems(visible, limit);
    const shownIds = new Set(shown.map(({ id }) => id));
    for (const node of nodes) node.hidden = !shownIds.has(node.dataset.id!);
    for (const { id } of visible) list.append(nodeById.get(id)!);
    more.hidden = remaining === 0;
    more.textContent = moreLabel(remaining);

    list.dataset.view = state.view;
    list.hidden = visible.length === 0;
    for (const button of viewButtons) {
      button.setAttribute('aria-pressed', String(button.dataset.view === state.view));
    }
    count.textContent = `${visible.length}개 스킬`;
    apply.textContent = `${visible.length}개 스킬 보기`;
    empty.hidden = visible.length > 0 && nodes.length > 0;

    const active = activeFilterCount(state);
    filterOpen.textContent = active > 0 ? `필터 ${active}` : '필터';
    for (const reset of resets) {
      reset.hidden = active === 0 && !state.query;
    }

    const query = serializeState(state, defaultSort).toString();
    history.replaceState({ limit }, '', query ? `?${query}` : location.pathname);
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
    sort.value = state.sort;
    for (const input of categoryInputs) input.checked = input.value === state.category;
  }

  syncControls();

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
      syncControls();
      renderFromStart();
      (filters.open ? apply : search).focus();
    });
  }
  more.addEventListener('click', () => {
    const firstNew = list.querySelectorAll<HTMLElement>('.skill:not([hidden])').length;
    limit += PAGE_SIZE;
    render();
    list.querySelectorAll<HTMLElement>('.skill:not([hidden])')[firstNew]
      ?.querySelector('a')
      ?.focus({ preventScroll: true });
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

  render();
}

const root = document.querySelector<HTMLElement>('[data-browse]');
if (root?.querySelector('.skill')) start(root);
