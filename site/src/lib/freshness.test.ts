import { describe, expect, it } from 'vitest';
import { isNewSkill } from './freshness';

describe('isNewSkill', () => {
  it('accepts skills seen within seven days', () => {
    expect(isNewSkill('2026-10-30', '2026-11-01', '2026-01-01')).toBe(true);
  });

  it('rejects older skills', () => {
    expect(isNewSkill('2026-10-20', '2026-11-01', '2026-01-01')).toBe(false);
  });

  it('rejects the initial catalog', () => {
    expect(isNewSkill('2026-10-30', '2026-11-01', '2026-10-30')).toBe(false);
  });

  it('rejects the eighth day boundary', () => {
    expect(isNewSkill('2026-10-25', '2026-11-01', null)).toBe(false);
  });
});
