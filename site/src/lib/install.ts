export type AgentId = 'claude-code' | 'codex' | 'cursor';

export interface InstallTarget {
  id: AgentId;
  label: string;
  personalDirectory: string;
  projectDirectory: string;
}

export const INSTALL_TARGETS: InstallTarget[] = [
  { id: 'claude-code', label: 'Claude Code', personalDirectory: '~/.claude/skills', projectDirectory: '.claude/skills' },
  { id: 'codex', label: 'Codex', personalDirectory: '~/.agents/skills', projectDirectory: '.agents/skills' },
  { id: 'cursor', label: 'Cursor', personalDirectory: '~/.cursor/skills', projectDirectory: '.cursor/skills' },
];

/** 저장소 경로는 외부 입력이다. 복사한 명령이 그대로 실행되므로 항상 인용한다. */
export function shellQuote(value: string): string {
  if (/^[A-Za-z0-9._/:-]+$/.test(value)) return value;
  return `'${value.replaceAll("'", `'\\''`)}'`;
}

export function skillFolderName(repository: string, path: string): string {
  const segments = path.split('/').slice(0, -1);
  const raw = segments.at(-1) ?? repository.split('/').at(-1) ?? 'skill';
  return raw.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[-.]+/, '') || 'skill';
}

function directoryExpression(directory: string): string {
  return directory.startsWith('~/') ? `"$HOME/${directory.slice(2)}"` : shellQuote(directory);
}

/** 저장소 전체가 아니라 스킬 폴더만 설치한다. */
export function installCommand(repository: string, path: string, directory: string): string {
  const url = shellQuote(`https://github.com/${repository}.git`);
  const name = skillFolderName(repository, path);
  const target = directoryExpression(directory);
  const skillDirectory = path.split('/').slice(0, -1).join('/');
  const source = skillDirectory ? `"$tmp"/${shellQuote(skillDirectory)}` : '"$tmp"';
  return [
    `tmp=$(mktemp -d) && git clone --depth 1 ${url} "$tmp"`,
    `mkdir -p ${target}`,
    `cp -R ${source} ${target}/${shellQuote(name)}`,
    'rm -rf "$tmp"',
  ].join('\n');
}
