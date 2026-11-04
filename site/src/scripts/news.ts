import { parseNewsState, serializeNewsState, type NewsState, type NewsTab, type ToolKey } from '../lib/news';

function start(root: HTMLElement): void {
  const tabs = [...root.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
  const panels = [...root.querySelectorAll<HTMLElement>('[data-news-panel]')];
  const toolInputs = [...root.querySelectorAll<HTMLInputElement>('input[name="tool"]')];
  const entries = [...root.querySelectorAll<HTMLElement>('[data-tool]')];
  const days = [...root.querySelectorAll<HTMLElement>('[data-day]')];
  const state: NewsState = parseNewsState(new URLSearchParams(location.search));

  function render(): void {
    for (const tab of tabs) {
      const selected = tab.dataset.tab === state.tab;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    }
    for (const panel of panels) panel.hidden = panel.dataset.newsPanel !== state.tab;
    for (const input of toolInputs) input.checked = input.value === state.tool;
    for (const entry of entries) entry.hidden = Boolean(state.tool) && entry.dataset.tool !== state.tool;
    // 고른 에이전트의 업데이트가 없는 날은 날짜째 숨긴다.
    for (const day of days) day.hidden = !day.querySelector('[data-tool]:not([hidden])');
    // 첫 화면용 CSS 규칙(페이지의 인라인 스크립트)과 같은 값을 유지한다.
    root.dataset.tab = state.tab;
    if (state.tool) root.dataset.tool = state.tool;
    else delete root.dataset.tool;
    const query = serializeNewsState(state).toString();
    history.replaceState(history.state, '', query ? `?${query}` : location.pathname);
  }

  function select(tab: NewsTab, focus = false): void {
    state.tab = tab;
    render();
    if (focus) tabs.find((button) => button.dataset.tab === tab)?.focus();
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => select(tab.dataset.tab as NewsTab));
    tab.addEventListener('keydown', (event) => {
      const targets: Record<string, number> = {
        ArrowRight: (index + 1) % tabs.length,
        ArrowLeft: (index - 1 + tabs.length) % tabs.length,
        Home: 0,
        End: tabs.length - 1,
      };
      const target = targets[event.key];
      if (target === undefined) return;
      event.preventDefault();
      const next = tabs[target]!;
      select(next.dataset.tab as NewsTab, true);
    });
  });
  for (const input of toolInputs) {
    input.addEventListener('change', () => {
      state.tool = input.value as ToolKey | '';
      render();
    });
  }

  render();
}

const root = document.querySelector<HTMLElement>('[data-news]');
if (root) start(root);
