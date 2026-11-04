import { describe, expect, it } from 'vitest';
import {
  countByCategory,
  countByTool,
  formatNewsDay,
  groupByDay,
  highlightHtml,
  notableNewSkills,
  parseNewsState,
  serializeNewsState,
  type ToolUpdate,
} from './news';

const update = (tool: ToolUpdate['tool'], date: string): ToolUpdate => ({
  tool,
  date,
  versions: ['1.0.0'],
  highlights: ['고쳤습니다.'],
  url: 'https://example.com',
});

describe('groupByDay', () => {
  it('puts the newest day first and keeps one tool order inside a day', () => {
    const days = groupByDay([update('cursor', '2026-11-03'), update('codex', '2026-11-04'), update('claude-code', '2026-11-04')]);
    expect(days.map(({ date }) => date)).toEqual(['2026-11-04', '2026-11-03']);
    expect(days[0]!.updates.map(({ tool }) => tool)).toEqual(['claude-code', 'codex']);
  });
});

describe('formatNewsDay', () => {
  it('reads the calendar date without a time zone shift', () => {
    expect(formatNewsDay('2026-11-04', '2026-11-05')).toEqual({ date: '11월 4일', weekday: '수요일' });
    expect(formatNewsDay('2026-10-05', '2026-11-05')).toEqual({ date: '10월 5일', weekday: '월요일' });
  });

  it('adds the year only for dates outside the current year', () => {
    expect(formatNewsDay('2026-12-30', '2027-01-02').date).toBe('2026년 12월 30일');
  });
});

describe('highlightHtml', () => {
  it('shows backticked commands as code and escapes everything else', () => {
    expect(highlightHtml('`claude mcp add`가 <b>고쳐졌습니다</b>')).toBe(
      '<code>claude mcp add</code>가 &lt;b&gt;고쳐졌습니다&lt;/b&gt;',
    );
  });

  it('leaves an unpaired backtick as text', () => {
    expect(highlightHtml('a ` b')).toBe('a ` b');
  });
});

describe('news URL state', () => {
  it('opens agent updates for all agents by default', () => {
    expect(parseNewsState(new URLSearchParams())).toEqual({ tab: 'tools', tool: '' });
    expect(serializeNewsState({ tab: 'tools', tool: '' }).toString()).toBe('');
  });

  it('keeps a known agent and the trends tab, and ignores the rest', () => {
    expect(parseNewsState(new URLSearchParams('tool=codex'))).toEqual({ tab: 'tools', tool: 'codex' });
    expect(parseNewsState(new URLSearchParams('tab=trends&tool=nope'))).toEqual({ tab: 'trends', tool: '' });
    expect(serializeNewsState({ tab: 'tools', tool: 'cursor' }).toString()).toBe('tool=cursor');
    expect(serializeNewsState({ tab: 'trends', tool: 'cursor' }).toString()).toBe('tab=trends');
  });
});

describe('countByTool', () => {
  it('counts entries per agent', () => {
    expect(countByTool([update('codex', '2026-11-04'), update('codex', '2026-11-03')])).toEqual({
      'claude-code': 0,
      codex: 2,
      cursor: 0,
    });
  });
});

describe('countByCategory', () => {
  it('lists the busiest field first and breaks ties by category order', () => {
    const skills = [{ category: 'design' }, { category: 'development' }, { category: 'design' }, { category: 'data' }] as const;
    expect(countByCategory([...skills])).toEqual([
      { category: 'design', count: 2 },
      { category: 'development', count: 1 },
      { category: 'data', count: 1 },
    ]);
  });
});

describe('notableNewSkills', () => {
  it('takes the best-ranked skill of each repository only', () => {
    const skills = [
      { rank: 3, repository: 'a/x', name: 'release' },
      { rank: 1, repository: 'a/x', name: 'top' },
      { rank: 2, repository: 'b/y', name: 'other' },
      { rank: 4, repository: 'c/z', name: 'third' },
    ];
    expect(notableNewSkills(skills, 2).map(({ name }) => name)).toEqual(['top', 'other']);
  });
});
