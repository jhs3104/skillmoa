import { describe, expect, it } from 'vitest';
import { licenseNotice, licenseStatus } from './license';

describe('licenseStatus', () => {
  it('treats well-known open source licenses as open', () => {
    for (const license of ['MIT', 'mit license', 'Apache-2.0', 'BSD-3-Clause', 'GPL-3.0-only', 'AGPL-3.0', 'CC0-1.0']) {
      expect(licenseStatus(license)).toBe('open');
    }
  });

  it('restricts proprietary terms even when they point to a license file', () => {
    expect(licenseStatus('Proprietary. LICENSE.txt has complete terms')).toBe('restricted');
    expect(licenseStatus('All rights reserved')).toBe('restricted');
  });

  it('asks for a check when the terms are missing or unknown', () => {
    expect(licenseStatus(null)).toBe('check');
    expect(licenseStatus('Complete terms in LICENSE.txt')).toBe('check');
    expect(licenseStatus('Custom license')).toBe('check');
  });
});

describe('licenseNotice', () => {
  it('stays quiet for open licenses', () => {
    expect(licenseNotice('MIT')).toBeNull();
  });

  it('explains why terms need checking', () => {
    expect(licenseNotice(null)).toContain('명시되지 않았습니다');
    expect(licenseNotice('Complete terms in LICENSE.txt')).toContain('LICENSE 파일');
  });

  it('says no install command is offered for restricted skills', () => {
    expect(licenseNotice('Proprietary')).toContain('설치 명령을 제공하지 않습니다');
  });
});
