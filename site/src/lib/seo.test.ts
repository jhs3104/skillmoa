import { describe, expect, it } from 'vitest';
import { INDEXABLE_MIN_STARS, isIndexable, truncate } from './seo';

describe('isIndexable', () => {
  it('uses the star threshold', () => {
    expect(isIndexable({ slug: 'a', stars: INDEXABLE_MIN_STARS })).toBe(true);
    expect(isIndexable({ slug: 'a', stars: INDEXABLE_MIN_STARS - 1 })).toBe(false);
  });
});

describe('truncate', () => {
  it('keeps short text unchanged', () => {
    expect(truncate('짧은 글', 10)).toBe('짧은 글');
  });

  it('stays within the limit', () => {
    expect(truncate('가'.repeat(200), 150)).toHaveLength(150);
  });
});
