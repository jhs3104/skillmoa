import { describe, expect, it } from 'vitest';
import type { CatalogItem } from './catalog';
import {
  parseAnswers,
  recommendSkills,
  scoreSkill,
  serializeAnswers,
  type Answers,
} from './questionnaire';

const item = (slug: string, fields: Partial<CatalogItem> = {}): CatalogItem => ({
  slug,
  name: slug,
  summary: '',
  useWhen: '',
  category: 'documents',
  roles: ['general'],
  difficulty: 'beginner',
  rank: 1,
  ...fields,
});

const answers = (fields: Partial<Answers> = {}): Answers => ({
  role: '',
  tool: '',
  goal: '',
  level: '',
  ...fields,
});

describe('recommendSkills', () => {
  it('ranks the goal above the role', () => {
    const goalMatch = item('goal', { category: 'design', roles: ['writer'], rank: 2 });
    const roleMatch = item('role', { category: 'data', roles: ['designer'], rank: 1 });
    const found = recommendSkills([roleMatch, goalMatch], answers({ goal: 'design', role: 'designer' }));
    expect(found.map(({ item: { slug } }) => slug)).toEqual(['goal', 'role']);
  });

  it('drops skills with no matching answer', () => {
    const found = recommendSkills([item('a', { category: 'data' })], answers({ goal: 'design' }));
    expect(found).toEqual([]);
  });

  it('penalizes skills harder than the chosen level', () => {
    const hard = scoreSkill(item('a', { difficulty: 'advanced' }), answers({ level: 'beginner' }), 1);
    const easy = scoreSkill(item('b', { difficulty: 'beginner' }), answers({ level: 'advanced' }), 1);
    expect(hard.score).toBeLessThan(easy.score);
  });

  it('uses rank to break ties', () => {
    const items = [item('b', { rank: 2 }), item('a', { rank: 1 })];
    const found = recommendSkills(items, answers({ goal: 'documents' }));
    expect(found[0]?.item.slug).toBe('a');
  });

  it('respects the limit', () => {
    const items = Array.from({ length: 9 }, (_, index) => item(String(index), { rank: index }));
    expect(recommendSkills(items, answers({ goal: 'documents' }))).toHaveLength(6);
  });
});

describe('shareable answers', () => {
  it('round-trips through the URL', () => {
    const chosen = answers({ role: 'designer', tool: 'cursor', goal: 'design', level: 'beginner' });
    expect(parseAnswers(serializeAnswers(chosen))).toEqual(chosen);
  });

  it('ignores tampered values', () => {
    expect(parseAnswers(new URLSearchParams('role=hacker&goal=x&tool=y&level=z'))).toEqual(answers());
  });
});
