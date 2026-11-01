import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';
import { installCommand, shellQuote, skillFolderName } from './install';

describe('shellQuote', () => {
  it('leaves plain paths readable', () => {
    expect(shellQuote('skills/pdf')).toBe('skills/pdf');
  });

  it.each(['$(touch pwned)', '`id`', "a'b", 'a b', '; rm -rf ~', '"x"'])(
    'keeps %s as one literal argument',
    (value) => {
      const output = execFileSync('sh', ['-c', `printf %s ${shellQuote(value)}`], { encoding: 'utf8' });
      expect(output).toBe(value);
    },
  );
});

describe('installCommand', () => {
  it('copies only the skill folder', () => {
    const command = installCommand('anthropics/skills', 'skills/pdf/SKILL.md', '~/.claude/skills');
    expect(command).toContain('git clone --depth 1 https://github.com/anthropics/skills.git');
    expect(command).toContain('cp -R "$tmp"/skills/pdf "$HOME/.claude/skills"/pdf');
  });

  it('installs a root skill under the repository name', () => {
    const command = installCommand('acme/kit', 'SKILL.md', '.cursor/skills');
    expect(command).toContain('cp -R "$tmp" .cursor/skills/kit');
  });

  it('quotes hostile paths from repositories', () => {
    const command = installCommand('acme/kit', 'x$(id)/SKILL.md', '.agents/skills');
    expect(command).toContain(`"$tmp"/'x$(id)'`);
    expect(command).toContain('.agents/skills/x-id-');
  });
});

describe('skillFolderName', () => {
  it('never produces a hidden or empty folder', () => {
    expect(skillFolderName('a/b', '../../SKILL.md')).toBe('skill');
    expect(skillFolderName('a/b', '.hidden/SKILL.md')).toBe('hidden');
  });
});
