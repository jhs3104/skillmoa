import type { CatalogItem } from '../lib/catalog';
import {
  parseAnswers,
  recommendSkills,
  serializeAnswers,
  type Answers,
} from '../lib/questionnaire';

const ERROR_MESSAGES: Record<string, string> = {
  invalid_question: '질문을 2자 이상 200자 이하로 적어 주세요.',
  rate_limited: '오늘 물어볼 수 있는 횟수를 모두 썼습니다. 내일 다시 시도하거나 위 질문을 이용해 주세요.',
  budget_exhausted: '오늘 처리할 수 있는 요청이 모두 찼습니다. 위 질문으로 찾아보세요.',
};
const UNAVAILABLE_MESSAGE = '지금은 문장 추천을 쓸 수 없습니다. 위 질문으로 찾아보세요.';

let catalogRequest: Promise<CatalogItem[]> | undefined;

function loadCatalog(): Promise<CatalogItem[]> {
  catalogRequest ??= fetch('/catalog.json').then((response) => response.json());
  return catalogRequest;
}

function renderResult(
  list: HTMLElement,
  item: CatalogItem,
  detail: string,
  query: string,
): void {
  const entry = document.createElement('li');
  entry.className = 'result-item';
  const title = document.createElement('h3');
  title.className = 'result-title';
  const link = document.createElement('a');
  link.href = `/skills/${item.slug}/${query}`;
  link.textContent = item.name;
  title.append(link);
  const why = document.createElement('p');
  why.className = 'result__why';
  why.textContent = detail;
  const summary = document.createElement('p');
  summary.textContent = item.useWhen;
  entry.append(title, why, summary);
  list.append(entry);
}

function startQuestionnaire(form: HTMLFormElement): void {
  const panel = form.querySelector<HTMLElement>('[data-result]')!;
  const status = form.querySelector<HTMLElement>('[data-result-status]')!;
  const list = form.querySelector<HTMLElement>('[data-result-list]')!;
  const share = form.querySelector<HTMLButtonElement>('[data-share]')!;

  async function show(answers: Answers): Promise<void> {
    const items = await loadCatalog();
    const results = recommendSkills(items, answers);
    list.replaceChildren();
    const query = answers.tool ? `?agent=${answers.tool}` : '';
    for (const { item, reasons } of results) {
      renderResult(list, item, reasons.join(' · '), query);
    }
    panel.hidden = false;
    share.hidden = results.length === 0;
    status.textContent = results.length > 0
      ? `${results.length}개 스킬을 찾았습니다.`
      : '맞는 스킬을 찾지 못했습니다. 다른 답변을 골라 보세요.';
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const params = new URLSearchParams();
    for (const [key, value] of new FormData(form)) params.set(key, String(value));
    const answers = parseAnswers(params);
    history.replaceState(null, '', `?${serializeAnswers(answers)}`);
    void show(answers);
  });

  share.addEventListener('click', async () => {
    await navigator.clipboard.writeText(location.href);
    share.textContent = '복사됨';
    setTimeout(() => (share.textContent = '결과 링크 복사'), 1500);
  });

  const initial = parseAnswers(new URLSearchParams(location.search));
  for (const [name, value] of Object.entries(initial)) {
    const input = form.querySelector<HTMLInputElement>(`input[name="${name}"][value="${value}"]`);
    if (input) input.checked = true;
  }
  if (Object.values(initial).some(Boolean)) void show(initial);
}

function startAsk(form: HTMLFormElement): void {
  const status = form.querySelector<HTMLElement>('[data-ask-status]')!;
  const list = form.querySelector<HTMLElement>('[data-ask-list]')!;
  const submit = form.querySelector<HTMLButtonElement>('button[type="submit"]')!;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const question = String(new FormData(form).get('question') ?? '');
    list.replaceChildren();
    status.textContent = '찾는 중입니다…';
    submit.disabled = true;
    try {
      const response = await fetch('/api/recommend/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const body = (await response.json()) as {
        error?: string;
        suggestions?: { slug: string; reason: string }[];
      };
      if (!response.ok) {
        status.textContent = ERROR_MESSAGES[body.error ?? ''] ?? UNAVAILABLE_MESSAGE;
        return;
      }
      const items = new Map((await loadCatalog()).map((item) => [item.slug, item]));
      const suggestions = body.suggestions ?? [];
      for (const { slug, reason } of suggestions) {
        const item = items.get(slug);
        if (item) renderResult(list, item, reason, '');
      }
      status.textContent = suggestions.length > 0
        ? `${suggestions.length}개 스킬을 찾았습니다.`
        : '맞는 스킬을 찾지 못했습니다. 조금 다르게 적어 보세요.';
    } catch {
      status.textContent = UNAVAILABLE_MESSAGE;
    } finally {
      submit.disabled = false;
    }
  });
}

const questionnaire = document.querySelector<HTMLFormElement>('[data-questionnaire]');
if (questionnaire) startQuestionnaire(questionnaire);
const ask = document.querySelector<HTMLFormElement>('[data-ask]');
if (ask) startAsk(ask);
