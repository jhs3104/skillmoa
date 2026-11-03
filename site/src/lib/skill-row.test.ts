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

  it('shows only what was found', () => {
    expect(skillRowHtml(item())).toContain('코드·네트워크 미확인');
    const flagged = skillRowHtml(item({ runsExternalCode: true, requiresExternalAccount: true, installBlocked: true }));
    expect(flagged).toContain('코드 실행');
    expect(flagged).toContain('외부 계정 필요');
    expect(flagged).toContain('설치 명령 없음');
    expect(flagged).not.toContain('미확인');
  });

  it('splits unflagged skills by the files in their folder', () => {
    expect(skillRowHtml(item({ scriptFiles: 'none' }))).toContain('지침 문서만');
    const scripts = skillRowHtml(item({ scriptFiles: 'present' }));
    expect(scripts).toContain('badge--caution">스크립트 포함');
    expect(skillRowHtml(item({ runsExternalCode: true, scriptFiles: 'none' }))).not.toContain('지침 문서만');
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
