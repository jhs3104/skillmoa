import { CATEGORY_LABELS } from './labels';
import { escapeHtml } from './skill-row';
import type { Category, Skill } from './types';

/** tool-updates.json과 news.json 계약 (collector/src/collector/export/schema.py). */
export type ToolKey = 'claude-code' | 'codex' | 'cursor';

export interface ToolUpdate {
  tool: ToolKey;
  date: string;
  versions: string[];
  highlights: string[];
  url: string;
}

export interface RisingRepository {
  fullName: string;
  starsGained: number;
  stars: number;
  windowDays: number;
}

export const TOOL_LABELS: Record<ToolKey, string> = {
  'claude-code': 'Claude Code',
  codex: 'Codex',
  cursor: 'Cursor',
};

export const TOOLS = Object.keys(TOOL_LABELS) as ToolKey[];

export type NewsTab = 'tools' | 'trends';

export interface NewsState {
  tab: NewsTab;
  tool: ToolKey | '';
}

export function parseNewsState(params: URLSearchParams): NewsState {
  const tool = params.get('tool') ?? '';
  return {
    tab: params.get('tab') === 'trends' ? 'trends' : 'tools',
    tool: (TOOLS as string[]).includes(tool) ? (tool as ToolKey) : '',
  };
}

/** 기본값은 주소에서 뺀다. 도구는 도구 업데이트 탭에서만 의미가 있다. */
export function serializeNewsState(state: NewsState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.tab === 'trends') params.set('tab', 'trends');
  else if (state.tool) params.set('tool', state.tool);
  return params;
}

export interface NewsDay {
  date: string;
  updates: ToolUpdate[];
}

/** 최신 날짜부터 온 기록을 날짜별로 묶는다. 같은 날 안의 도구 순서는 고정한다. */
export function groupByDay(updates: ToolUpdate[]): NewsDay[] {
  const days = new Map<string, ToolUpdate[]>();
  for (const update of updates) {
    days.set(update.date, [...(days.get(update.date) ?? []), update]);
  }
  return [...days.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([date, entries]) => ({
      date,
      updates: entries.sort((a, b) => TOOLS.indexOf(a.tool) - TOOLS.indexOf(b.tool)),
    }));
}

const WEEKDAYS = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];

/**
 * 기록의 날짜는 시간대 없는 달력 날짜다. UTC로 읽어 요일이 하루 밀리지 않게 한다.
 * 올해가 아닌 날짜에만 연도를 붙인다. 기록이 해를 넘기면 12월과 1월이 섞이기 때문이다.
 */
export function formatNewsDay(isoDate: string, today: string): { date: string; weekday: string } {
  const [year, month, day] = isoDate.split('-').map(Number) as [number, number, number];
  const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()]!;
  const prefix = today.startsWith(`${year}-`) ? '' : `${year}년 `;
  return { date: `${prefix}${month}월 ${day}일`, weekday };
}

/** 요약 문장의 `명령`만 코드로 보여 준다. 나머지는 모두 글자로 이스케이프한다. */
export function highlightHtml(text: string): string {
  return escapeHtml(text).replace(/`([^`]+)`/g, '<code>$1</code>');
}

export function countByTool(updates: ToolUpdate[]): Record<ToolKey, number> {
  const counts = { 'claude-code': 0, codex: 0, cursor: 0 };
  for (const update of updates) counts[update.tool] += 1;
  return counts;
}

export interface CategoryCount {
  category: Category;
  count: number;
}

/** 새 스킬이 많이 나온 분야부터. 개수가 같으면 카테고리 순서를 따른다. */
export function countByCategory(skills: Pick<Skill, 'category'>[]): CategoryCount[] {
  const order = Object.keys(CATEGORY_LABELS) as Category[];
  const counts = new Map<Category, number>();
  for (const { category } of skills) counts.set(category, (counts.get(category) ?? 0) + 1);
  return [...counts.entries()]
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count || order.indexOf(a.category) - order.indexOf(b.category));
}

/** 대표순으로 고르되 저장소마다 하나만 싣는다. 한 저장소가 목록을 채우지 않게 한다. */
export function notableNewSkills<T extends Pick<Skill, 'rank' | 'repository'>>(skills: T[], limit: number): T[] {
  const seen = new Set<string>();
  return [...skills]
    .sort((a, b) => a.rank - b.rank)
    .filter(({ repository }) => !seen.has(repository) && Boolean(seen.add(repository)))
    .slice(0, limit);
}
