import type { CatalogItem } from '../lib/catalog';
import {
  hasMatchingAnswer,
  parseAnswers,
  recommendSkills,
  serializeAnswers,
  type Answers,
} from '../lib/questionnaire';

const ERROR_MESSAGES: Record<string, string> = {
  invalid_question: '하고 싶은 일을 2자 이상 200자 이하로 적어 주세요.',
  rate_limited: '오늘 이 인터넷 연결에서 쓸 수 있는 5번을 모두 썼습니다. 오전 9시 이후에 다시 쓰거나 맞춤 추천을 이용해 주세요.',
  budget_exhausted: '오늘 AI 찾기 사용량이 다 찼습니다. 전체 스킬이나 맞춤 추천으로 찾아보세요.',
};
const UNAVAILABLE_MESSAGE = '지금은 AI 찾기를 쓸 수 없습니다. 전체 스킬이나 맞춤 추천으로 찾아보세요.';
const CATALOG_ERROR_MESSAGE = '스킬 목록을 불러오지 못했습니다. 다시 눌러 주세요.';
const SAVED_ASK_KEY = 'ask-result';

interface Suggestion {
  slug: string;
  reason: string;
}

interface SkillRow extends Suggestion {
  query?: string;
}

interface SavedAsk {
  question: string;
  suggestions: Suggestion[];
  scrollY?: number;
}

let catalogRequest: Promise<CatalogItem[]> | undefined;

/** 결과는 주소에 담을 수 없어, 상세에서 돌아와도 남도록 이 탭에만 보관한다. */
function readSavedAsk(): SavedAsk | null {
  try {
    const saved = sessionStorage.getItem(SAVED_ASK_KEY);
    return saved ? (JSON.parse(saved) as SavedAsk) : null;
  } catch {
    return null;
  }
}

function writeSavedAsk(saved: SavedAsk | null): void {
  try {
    if (saved) sessionStorage.setItem(SAVED_ASK_KEY, JSON.stringify(saved));
    else sessionStorage.removeItem(SAVED_ASK_KEY);
  } catch {
    // 보관하지 못해도 지금 화면의 결과는 그대로 보인다.
  }
}

function loadCatalog(): Promise<CatalogItem[]> {
  catalogRequest ??= fetch('/catalog.json')
    .then((response) => {
      if (!response.ok) throw new Error(`catalog: ${response.status}`);
      return response.json() as Promise<CatalogItem[]>;
    })
    .catch((error: unknown) => {
      catalogRequest = undefined;
      throw error;
    });
  return catalogRequest;
}

/** 목록과 같은 모양을 유지하도록 빌드된 스킬 행을 복제한다. 없는 슬러그는 버린다. */
function showSkills(rows: SkillRow[]): number {
  const results = document.querySelector<HTMLElement>('[data-results]')!;
  const list = results.querySelector<HTMLElement>('[data-results-list]')!;
  const template = document.querySelector<HTMLTemplateElement>('[data-skill-rows]')!;
  const sources = new Map(
    [...template.content.querySelectorAll<HTMLElement>('.skill')].map((row) => [row.dataset.id, row]),
  );

  list.querySelectorAll('.skill').forEach((row) => row.remove());
  for (const { slug, reason, query = '' } of rows) {
    const source = sources.get(slug);
    if (!source) continue;
    const row = source.cloneNode(true) as HTMLElement;
    const link = row.querySelector('a')!;
    link.setAttribute('href', `${link.getAttribute('href')}${query}`);
    const why = document.createElement('p');
    why.className = 'skill__reason';
    why.textContent = reason;
    row.querySelector('.skill__title')!.after(why);
    list.append(row);
  }

  const shown = list.querySelectorAll('.skill').length;
  results.hidden = shown === 0;
  return shown;
}

function scrollToStatus(status: HTMLElement): void {
  const motion = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
  status.scrollIntoView({ block: 'start', behavior: motion });
}

function startQuestionnaire(form: HTMLFormElement): void {
  const status = form.querySelector<HTMLElement>('[data-result-status]')!;
  const share = document.querySelector<HTMLButtonElement>('[data-share]')!;

  function askForAnswer(): void {
    showSkills([]);
    status.textContent = '하는 일, 하고 싶은 일, 난이도 중 하나 이상을 골라 주세요. 도구는 설치 명령을 고르는 데만 씁니다.';
  }

  async function show(answers: Answers): Promise<void> {
    let items: CatalogItem[];
    try {
      items = await loadCatalog();
    } catch {
      showSkills([]);
      status.textContent = CATALOG_ERROR_MESSAGE;
      return;
    }
    const query = answers.tool ? `?agent=${answers.tool}` : '';
    const shown = showSkills(recommendSkills(items, answers).map(({ item, reasons }) => ({
      slug: item.slug,
      reason: reasons.join(' · '),
      query,
    })));
    status.textContent = shown > 0
      ? `${shown}개 스킬을 찾았습니다.`
      : '맞는 스킬을 찾지 못했습니다. 다른 답변을 골라 보세요.';
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const params = new URLSearchParams();
    for (const [key, value] of new FormData(form)) params.set(key, String(value));
    const answers = parseAnswers(params);
    if (!hasMatchingAnswer(answers)) {
      askForAnswer();
      return;
    }
    history.replaceState(null, '', `?${serializeAnswers(answers)}`);
    void show(answers).then(() => scrollToStatus(status));
  });

  share.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      share.textContent = '복사됨';
    } catch {
      share.textContent = '주소창의 링크를 복사해 주세요';
    }
    setTimeout(() => (share.textContent = '결과 링크 복사'), 2000);
  });

  const initial = parseAnswers(new URLSearchParams(location.search));
  for (const [name, value] of Object.entries(initial)) {
    const input = form.querySelector<HTMLInputElement>(`input[name="${name}"][value="${value}"]`);
    if (input) input.checked = true;
  }
  if (hasMatchingAnswer(initial)) void show(initial);
}

function startAsk(form: HTMLFormElement): void {
  const status = form.querySelector<HTMLElement>('[data-ask-status]')!;
  const submit = form.querySelector<HTMLButtonElement>('button[type="submit"]')!;
  const input = form.querySelector<HTMLTextAreaElement>('textarea')!;
  const recover = form.querySelector<HTMLElement>('[data-ask-recover]')!;

  function showSuggestions(suggestions: Suggestion[]): number {
    const shown = showSkills(suggestions);
    status.textContent = shown > 0
      ? `${shown}개 스킬을 찾았습니다.`
      : '맞는 스킬을 찾지 못했습니다. 조금 다르게 적어 보세요.';
    return shown;
  }

  const saved = readSavedAsk();
  if (saved) {
    input.value = saved.question;
    showSuggestions(saved.suggestions);
    window.scrollTo(0, saved.scrollY ?? 0);
  }

  window.addEventListener('pagehide', () => {
    const current = readSavedAsk();
    if (current) writeSavedAsk({ ...current, scrollY: window.scrollY });
  });

  input.addEventListener('keydown', (event) => {
    const composing = event.isComposing || event.keyCode === 229;
    if (event.key === 'Enter' && !event.shiftKey && !composing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.querySelectorAll<HTMLButtonElement>('[data-ask-example]').forEach((example) => {
    example.addEventListener('click', () => {
      input.value = example.textContent ?? '';
      input.focus();
    });
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (submit.getAttribute('aria-disabled') === 'true') return;
    const question = String(new FormData(form).get('question') ?? '');
    recover.hidden = true;
    status.textContent = '찾는 중입니다…';
    submit.setAttribute('aria-disabled', 'true');
    try {
      const response = await fetch('/api/recommend/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const body = (await response.json()) as { error?: string; suggestions?: Suggestion[] };
      if (!response.ok) {
        status.textContent = ERROR_MESSAGES[body.error ?? ''] ?? UNAVAILABLE_MESSAGE;
        recover.hidden = false;
        return;
      }
      const suggestions = body.suggestions ?? [];
      const shown = showSuggestions(suggestions);
      writeSavedAsk({ question, suggestions });
      if (shown > 0) scrollToStatus(status);
    } catch {
      status.textContent = UNAVAILABLE_MESSAGE;
      recover.hidden = false;
    } finally {
      submit.removeAttribute('aria-disabled');
    }
  });
}

const questionnaire = document.querySelector<HTMLFormElement>('[data-questionnaire]');
if (questionnaire) startQuestionnaire(questionnaire);
const ask = document.querySelector<HTMLFormElement>('[data-ask]');
if (ask) startAsk(ask);
