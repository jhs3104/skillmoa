import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { ADSENSE_CLIENT } from './labels';

describe('AdSense publisher', () => {
  it('uses a ca-pub client id', () => {
    expect(ADSENSE_CLIENT).toMatch(/^ca-pub-\d{16}$/);
  });

  it('lists the same publisher in ads.txt', () => {
    const adsTxt = readFileSync(new URL('../../public/ads.txt', import.meta.url), 'utf-8');
    const publisher = ADSENSE_CLIENT.replace(/^ca-/, '');
    expect(adsTxt.trim()).toBe(`google.com, ${publisher}, DIRECT, f08c47fec0942fa0`);
  });
});
