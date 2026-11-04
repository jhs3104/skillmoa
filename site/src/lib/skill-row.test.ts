import { describe, expect, it } from 'vitest';
import type { CatalogItem } from './catalog';
import { skillRowHtml } from './skill-row';

const item = (fields: Partial<CatalogItem> = {}): CatalogItem => ({
  slug: 'acme--kit--pdf',
  rank: 1,
  name: 'pdf',
  repository: 'acme/kit',
  summary: '요약',
  useWhen: '문서가 필요할 때',
  category: 'documents',
  subcategory: 'pdf',
  roles: ['general'],
  useCases: ['PDF 편집'],
  difficulty: 'beginner',
  stars: 1200,
  pushedAt: '2026-10-28',
  firstSeenAt: '2026-11-01',
  runsExternalCode: false,
  accessesNetwork: false,
  requiresExternalAccount: false,
  scriptFiles: 'unknown',
  installBlocked: false,
  ...fields,
});

describe('skillRowHtml', () => {
  it('escapes collected text', () => {
    const html = skillRowHtml(item({ name: '<img src=x onerror=alert(1)>', summary: '"quote" & more' }));
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
    expect(html).toContain('&quot;quote&quot; &amp; more');
  });

  it('escapes the recommendation reason and keeps it in the row', () => {
    const html = skillRowHtml(item(), { reason: '<b>맞습니다</b>' });
    expect(html).toContain('skill__reason');
    expect(html).toContain('&lt;b&gt;');
  });

  it('adds the agent to the detail link', () => {
    expect(skillRowHtml(item(), { query: '?agent=codex' })).toContain('href="/skills/acme--kit--pdf/?agent=codex"');
  });

  it('marks skills that need an account or API key in the title line', () => {
    const row = skillRowHtml(item({ requiresExternalAccount: true, installBlocked: true }));
    const title = row.slice(row.indexOf('skill__title'), row.indexOf('skill__summary'));
    expect(title).toMatch(/badge--caution" title="AI가 SKILL\.md[^"]*">계정·API 키 필요</);
    expect(title).toContain('설치 명령 없음');
    expect(skillRowHtml(item())).not.toContain('계정·API 키 필요');
  });

  it('leaves code and network judgement to the detail page', () => {
    for (const flags of [
      { runsExternalCode: true, accessesNetwork: true },
      { scriptFiles: 'none' as const },
      { scriptFiles: 'present' as const },
      {},
    ]) {
      const row = skillRowHtml(item(flags));
      for (const label of ['코드 실행', '네트워크', '지침 문서만', '스크립트 포함', '미확인']) {
        expect(row).not.toContain(label);
      }
    }
  });

  it('names the subcategory when the summary has one', () => {
    expect(skillRowHtml(item())).toContain('<span class="skill__sub">PDF</span>');
    expect(skillRowHtml(item({ subcategory: null }))).not.toContain('skill__sub');
  });

  it('switches the date for new skills', () => {
    const html = skillRowHtml(item(), { dateKind: 'found' });
    expect(html).toContain('발견일');
    expect(html).toContain('2026.11.01');
  });
});
