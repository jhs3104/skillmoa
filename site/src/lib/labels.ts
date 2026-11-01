import type { Category, Difficulty, Role } from './types';

export const SITE_NAME = '스킬서가';

export const CATEGORY_LABELS: Record<Category, string> = {
  development: '개발',
  testing: '테스트',
  devops: '배포·운영',
  data: '데이터',
  documents: '문서',
  design: '디자인',
  writing: '글쓰기',
  marketing: '마케팅',
  productivity: '생산성',
  research: '리서치',
  security: '보안',
  'ai-agents': 'AI 에이전트',
  other: '기타',
};

export const ROLE_LABELS: Record<Role, string> = {
  developer: '개발자',
  designer: '디자이너',
  data: '데이터 분석가',
  product: '기획자·PM',
  marketer: '마케터',
  writer: '작가·에디터',
  researcher: '연구자',
  general: '누구나',
};

export const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  beginner: '입문',
  intermediate: '중급',
  advanced: '고급',
};

const compact = new Intl.NumberFormat('ko-KR', { notation: 'compact', maximumFractionDigits: 1 });

export function formatStars(stars: number): string {
  return compact.format(stars);
}

export function formatDate(isoDate: string): string {
  return isoDate.replaceAll('-', '.');
}
