import type { Category, Difficulty, Role } from './types';

export const SITE_NAME = '스킬모아';
export const HOME_TITLE = '스킬을 한눈에 스킬모아';
/** 저작자의 삭제·수정 요청을 받는 공개 메일. 비어 있으면 푸터에 표시하지 않는다. */
export const CONTACT_EMAIL: string = 'contact@skillmoa.com';
export const STAR_PATH = 'M8 1.2 10.1 5.6l4.8.6-3.5 3.3.9 4.8L8 12l-4.3 2.3.9-4.8L1.1 6.2l4.8-.6Z';

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

/** SKILL.md의 license 칸은 자유 문구라 라이선스 이름이 아닌 값이 많다. */
export function formatLicense(license: string | null): string {
  if (!license) return '명시되지 않음';
  if (/proprietary/i.test(license)) return '독점 라이선스 (LICENSE 파일 참고)';
  if (/license\.(txt|md)/i.test(license)) return 'LICENSE 파일 참고';
  return license;
}
