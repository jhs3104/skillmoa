import { describe, expect, it } from 'vitest';
import type { CatalogItem } from './catalog';
import {
  hasMatchingAnswer,
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
  repository: 'acme/kit',
  useCases: [],
  stars: 1,
  pushedAt: '2026-01-01',
  firstSeenAt: '2026-01-01',
  runsExternalCode: false,
  accessesNetwork: false,
  requiresExternalAccount: false,
  installBlocked: false,
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
  it('ranks a role match above a level match when no goal is chosen', () => {
    const levelMatch = item('level', { roles: ['writer'], rank: 1 });
    const roleMatch = item('role', { roles: ['designer'], difficulty: 'advanced', rank: 2 });
    const found = recommendSkills([levelMatch, roleMatch], answers({ role: 'designer', level: 'advanced' }));
    expect(found[0]?.item.slug).toBe('role');
  });

  it('keeps only skills for the chosen goal', () => {
    const goalMatch = item('goal', { category: 'design', roles: ['writer'], rank: 2 });
    const levelOnly = item('level', { category: 'documents', difficulty: 'beginner', rank: 1 });
    const roleOnly = item('role', { category: 'data', roles: ['designer'], rank: 1 });
    const found = recommendSkills(
      [levelOnly, roleOnly, goalMatch],
      answers({ goal: 'design', role: 'designer', level: 'beginner' }),
    );
    expect(found.map(({ item: { slug } }) => slug)).toEqual(['goal']);
  });

  it('drops skills with no matching answer', () => {
    const found = recommendSkills([item('a', { category: 'data' })], answers({ goal: 'design' }));
    expect(found).toEqual([]);
  });

  it('states a fit, not an endorsement, for a role match', () => {
    const [found] = recommendSkills([item('a', { roles: ['designer'] })], answers({ role: 'designer' }));
    expect(found?.reasons).toEqual(['디자이너에게 맞음']);
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

describe('hasMatchingAnswer', () => {
  it('does not count the install tool as something to match', () => {
    expect(hasMatchingAnswer(answers({ tool: 'codex' }))).toBe(false);
    expect(hasMatchingAnswer(answers({ tool: 'codex', goal: 'design' }))).toBe(true);
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
