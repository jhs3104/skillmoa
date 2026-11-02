import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { installCommand, installLocation, shellQuote, skillFolderName } from './install';

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
    expect(command).toContain('cp -R "$tmp"/skills/pdf/. "$HOME/.claude/skills"/pdf/');
  });

  it('installs a root skill under the repository name', () => {
    const command = installCommand('acme/kit', 'SKILL.md', '.cursor/skills');
    expect(command).toContain('cp -R "$tmp"/. .cursor/skills/kit/');
  });

  it('stays flat when the same skill is installed twice', () => {
    const root = mkdtempSync(join(tmpdir(), 'install-test-'));
    try {
      mkdirSync(join(root, 'clone/skills/pdf'), { recursive: true });
      writeFileSync(join(root, 'clone/skills/pdf/SKILL.md'), 'x');
      const copySteps = installCommand('a/b', 'skills/pdf/SKILL.md', '.agents/skills')
        .split('\n')
        .slice(1, 3)
        .join('\n');
      const script = `tmp=clone\n${copySteps}`;
      execFileSync('sh', ['-c', script], { cwd: root });
      execFileSync('sh', ['-c', script], { cwd: root });
      expect(existsSync(join(root, '.agents/skills/pdf/SKILL.md'))).toBe(true);
      expect(existsSync(join(root, '.agents/skills/pdf/pdf'))).toBe(false);
    } finally {
      rmSync(root, { recursive: true });
    }
  });

  it('quotes hostile paths from repositories', () => {
    const command = installCommand('acme/kit', 'x$(id)/SKILL.md', '.agents/skills');
    expect(command).toContain(`"$tmp"/'x$(id)'`);
    expect(command).toContain('.agents/skills/x-id-');
  });
});

describe('installLocation', () => {
  it('names the folder the command creates', () => {
    expect(installLocation('a/b', 'skills/pdf/SKILL.md', '~/.claude/skills')).toBe('~/.claude/skills/pdf');
  });
});

describe('skillFolderName', () => {
  it('never produces a hidden or empty folder', () => {
    expect(skillFolderName('a/b', '../../SKILL.md')).toBe('skill');
    expect(skillFolderName('a/b', '.hidden/SKILL.md')).toBe('hidden');
  });
});
