import taxonomy from '../data/taxonomy.json';
import type { Category, Difficulty, Role, Subcategory } from './types';

export const SITE_NAME = '스킬모아';
export const HOME_TITLE = '스킬모아 | AI 에이전트 스킬 모음';
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

/** 세부 분류의 표시 이름. 목록과 순서의 원본은 collector가 생성한 taxonomy.json이다. */
export const SUBCATEGORY_LABELS: Record<Subcategory, string> = {
  frontend: '프론트엔드',
  backend: '백엔드',
  mobile: '모바일',
  git: 'Git',
  'code-quality': '코드 품질',
  debugging: '디버깅',
  'dev-tools': '개발 도구',
  'game-dev': '게임 개발',
  web3: 'Web3',
  'test-writing': '테스트 작성',
  'browser-testing': '브라우저 테스트',
  qa: 'QA',
  deployment: '배포·CI',
  infrastructure: '인프라',
  monitoring: '모니터링',
  release: '릴리스',
  'data-analysis': '데이터 분석',
  database: '데이터베이스',
  'machine-learning': '머신러닝',
  visualization: '시각화',
  pdf: 'PDF',
  office: '워드·엑셀',
  presentation: '프레젠테이션',
  diagram: '다이어그램',
  'ui-ux': 'UI·UX',
  'visual-design': '시각 디자인',
  image: '이미지',
  video: '영상',
  accessibility: '접근성',
  drafting: '원고·초안',
  translation: '번역',
  editing: '교정·윤문',
  seo: 'SEO',
  'social-media': '소셜 미디어',
  advertising: '광고·카피',
  sales: '영업',
  ecommerce: '이커머스',
  communication: '메일·메신저',
  'notes-calendar': '일정·메모',
  'project-management': '프로젝트 관리',
  automation: '업무 자동화',
  learning: '학습',
  'web-research': '자료 조사',
  academic: '논문·학술',
  'market-research': '시장 조사',
  'security-review': '보안 점검',
  vulnerability: '취약점',
  auth: '인증·권한',
  'skill-authoring': '스킬 만들기',
  mcp: 'MCP·연동',
  'agent-operations': '에이전트 운영',
  'ai-engineering': 'AI 엔지니어링',
  persona: '페르소나',
  finance: '금융·회계',
  legal: '법률',
  health: '건강·의료',
  'business-ops': '비즈니스 운영',
  audio: '오디오·음악',
  lifestyle: '생활·여행',
  misc: '그 밖',
};

/** 대분류마다 세부 분류를 collector가 정한 순서대로 담는다. */
export const SUBCATEGORIES = taxonomy as Record<Category, Subcategory[]>;

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
