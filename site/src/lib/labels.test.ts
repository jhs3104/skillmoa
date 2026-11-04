import { describe, expect, it } from 'vitest';
import taxonomy from '../data/taxonomy.json';
import { CATEGORY_LABELS, formatCount, formatLicense, SUBCATEGORY_LABELS } from './labels';

describe('formatCount', () => {
  it('groups thousands with commas', () => {
    expect(formatCount(3807)).toBe('3,807');
    expect(formatCount(19000)).toBe('19,000');
  });

  it('leaves small numbers as they are', () => {
    expect(formatCount(0)).toBe('0');
    expect(formatCount(214)).toBe('214');
  });
});

describe('formatLicense', () => {
  it('keeps license names as they are', () => {
    expect(formatLicense('MIT')).toBe('MIT');
  });

  it('says so when no license is given', () => {
    expect(formatLicense(null)).toBe('명시되지 않음');
  });

  it('replaces free-form pointers to a license file', () => {
    expect(formatLicense('Complete terms in LICENSE.txt')).toBe('LICENSE 파일 참고');
    expect(formatLicense('Proprietary. LICENSE.txt has complete terms')).toBe('독점 라이선스 (LICENSE 파일 참고)');
  });
});

describe('taxonomy labels', () => {
  it('names every subcategory that the collector can produce', () => {
    const fromCollector = Object.values(taxonomy).flat();
    const named = Object.keys(SUBCATEGORY_LABELS);
    expect(fromCollector.filter((subcategory) => !named.includes(subcategory))).toEqual([]);
  });

  it('keeps names beyond the taxonomy only for subcategories older skills may still carry', () => {
    const fromCollector: string[] = Object.values(taxonomy).flat();
    const extra = Object.keys(SUBCATEGORY_LABELS).filter((name) => !fromCollector.includes(name));
    expect(extra.sort()).toEqual(['audio', 'finance', 'legal']);
  });

  it('groups subcategories under the same categories the site knows', () => {
    expect(Object.keys(taxonomy).sort()).toEqual(Object.keys(CATEGORY_LABELS).sort());
  });
});
