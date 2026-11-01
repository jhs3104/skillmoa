import type { CatalogItem } from './catalog';
import type { AgentId } from './install';
import { ROLE_LABELS } from './labels';
import type { Category, Difficulty, Role } from './types';

export interface Goal {
  id: string;
  label: string;
  categories: Category[];
}

export const GOALS: Goal[] = [
  { id: 'code', label: '코드 작성·리뷰', categories: ['development', 'testing'] },
  { id: 'ops', label: '배포·운영·보안', categories: ['devops', 'security'] },
  { id: 'documents', label: '문서·보고서 작성', categories: ['documents', 'writing'] },
  { id: 'design', label: '디자인·시각 자료', categories: ['design'] },
  { id: 'data', label: '데이터 분석·리서치', categories: ['data', 'research'] },
  { id: 'marketing', label: '마케팅·콘텐츠', categories: ['marketing', 'writing'] },
  { id: 'agents', label: '에이전트 운영·자동화', categories: ['ai-agents', 'productivity'] },
];

export interface Answers {
  role: Role | '';
  tool: AgentId | '';
  goal: string;
  level: Difficulty | '';
}

export interface ScoredSkill {
  item: CatalogItem;
  score: number;
  reasons: string[];
}

const LEVELS: Difficulty[] = ['beginner', 'intermediate', 'advanced'];
const WEIGHTS = { goal: 5, role: 3, generalRole: 1, exactLevel: 2, easierLevel: 1, harderLevel: -3 };

export function parseAnswers(params: URLSearchParams): Answers {
  const role = params.get('role') ?? '';
  const tool = params.get('tool') ?? '';
  const goal = params.get('goal') ?? '';
  const level = params.get('level') ?? '';
  return {
    role: role in ROLE_LABELS ? (role as Role) : '',
    tool: ['claude-code', 'codex', 'cursor'].includes(tool) ? (tool as AgentId) : '',
    goal: GOALS.some(({ id }) => id === goal) ? goal : '',
    level: LEVELS.includes(level as Difficulty) ? (level as Difficulty) : '',
  };
}

export function serializeAnswers(answers: Answers): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(answers)) {
    if (value) params.set(key, value);
  }
  return params;
}

export function scoreSkill(item: CatalogItem, answers: Answers, total: number): ScoredSkill {
  let score = 0;
  const reasons: string[] = [];

  const goal = GOALS.find(({ id }) => id === answers.goal);
  if (goal?.categories.includes(item.category)) {
    score += WEIGHTS.goal;
    reasons.push(goal.label);
  }

  if (answers.role && item.roles.includes(answers.role)) {
    score += WEIGHTS.role;
    reasons.push(`${ROLE_LABELS[answers.role]} 추천`);
  } else if (answers.role && item.roles.includes('general')) {
    score += WEIGHTS.generalRole;
  }

  if (answers.level) {
    const gap = LEVELS.indexOf(item.difficulty) - LEVELS.indexOf(answers.level);
    if (gap === 0) {
      score += WEIGHTS.exactLevel;
      reasons.push('난이도 맞음');
    } else {
      score += gap < 0 ? WEIGHTS.easierLevel : WEIGHTS.harderLevel;
    }
  }

  const popularity = total > 0 ? 1 - item.rank / (total + 1) : 0;
  return { item, score: score + popularity, reasons };
}

/** 답변과 맞는 근거가 하나도 없는 스킬은 인기만으로 올리지 않는다. */
export function recommendSkills(items: CatalogItem[], answers: Answers, limit = 6): ScoredSkill[] {
  return items
    .map((item) => scoreSkill(item, answers, items.length))
    .filter(({ reasons }) => reasons.length > 0)
    .sort((a, b) => b.score - a.score || a.item.rank - b.item.rank)
    .slice(0, limit);
}
