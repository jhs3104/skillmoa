import {
  parseState,
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
  const local = root.querySelector<HTMLInputElement>('input[name="local"]')!;
  const filters = root.querySelector<HTMLDialogElement>('[data-filters]')!;
  const viewButtons = [...root.querySelectorAll<HTMLButtonElement>('[data-view]:not(ol)')];
  const categories = (root.dataset.categories ?? '').split(',').filter(Boolean);

  const items: BrowseItem[] = nodes.map((node) => ({
    id: node.dataset.id!,
    text: node.dataset.text!,
    category: node.dataset.category as Category,
    rank: Number(node.dataset.rank),
    pushedAt: node.dataset.pushed!,
    firstSeenAt: node.dataset.firstSeen!,
    runsNothing: node.dataset.local === '1',
  }));
  const nodeById = new Map(nodes.map((node) => [node.dataset.id!, node]));
  const state: BrowseState = parseState(new URLSearchParams(location.search), categories);

  function render(): void {
    const visible = visibleItems(items, state);
    const shown = new Set(visible.map(({ id }) => id));
    for (const node of nodes) node.hidden = !shown.has(node.dataset.id!);
    for (const { id } of visible) list.append(nodeById.get(id)!);

    list.dataset.view = state.view;
    for (const button of viewButtons) {
      button.setAttribute('aria-pressed', String(button.dataset.view === state.view));
    }
    count.textContent = `${visible.length}개 스킬`;
    empty.hidden = visible.length > 0 || nodes.length === 0;

    const query = serializeState(state).toString();
    history.replaceState(null, '', query ? `?${query}` : location.pathname);
  }

  search.value = state.query;
  sort.value = state.sort;
  local.checked = state.localOnly;
  root.querySelector<HTMLInputElement>(`input[name="category"][value="${state.category}"]`)!.checked = true;

  search.addEventListener('input', () => {
    state.query = search.value;
    render();
  });
  sort.addEventListener('change', () => {
    state.sort = sort.value as SortKey;
    render();
  });
  local.addEventListener('change', () => {
    state.localOnly = local.checked;
    render();
  });
  root.querySelectorAll<HTMLInputElement>('input[name="category"]').forEach((input) => {
    input.addEventListener('change', () => {
      state.category = input.value as Category | '';
      render();
    });
  });
  for (const button of viewButtons) {
    button.addEventListener('click', () => {
      state.view = button.dataset.view as ViewKey;
      render();
    });
  }

  root.querySelector('[data-filters-open]')!.addEventListener('click', () => filters.showModal());
  root.querySelector('[data-filters-close]')!.addEventListener('click', () => filters.close());
  filters.addEventListener('click', (event) => {
    if (event.target === filters) filters.close();
  });
  window.matchMedia(WIDE_SCREEN).addEventListener('change', () => filters.close());

  render();
}

const root = document.querySelector<HTMLElement>('[data-browse]');
if (root) start(root);
