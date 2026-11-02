import { describe, expect, it } from 'vitest';
import { formatLicense } from './labels';

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
