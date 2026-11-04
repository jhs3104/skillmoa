/** skills.schema.json과 같은 계약이다. 스키마를 바꾸면 함께 바꾼다. */

export type Category =
  | 'development' | 'testing' | 'devops' | 'data' | 'documents' | 'design' | 'writing'
  | 'marketing' | 'productivity' | 'research' | 'security' | 'ai-agents' | 'finance' | 'audio'
  | 'legal' | 'health-lifestyle' | 'other';

export type Role =
  | 'developer' | 'designer' | 'data' | 'product' | 'marketer' | 'writer' | 'researcher' | 'general';

export type Difficulty = 'beginner' | 'intermediate' | 'advanced';

export interface SiteRepository {
  fullName: string;
  stars: number;
  pushedAt: string;
  license: string | null;
  defaultBranch: string;
}

export type Subcategory =
  | 'frontend'
  | 'backend'
  | 'mobile'
  | 'git'
  | 'code-quality'
  | 'debugging'
  | 'dev-tools'
  | 'game-dev'
  | 'web3'
  | 'test-writing'
  | 'browser-testing'
  | 'qa'
  | 'deployment'
  | 'infrastructure'
  | 'monitoring'
  | 'release'
  | 'data-analysis'
  | 'database'
  | 'machine-learning'
  | 'visualization'
  | 'pdf'
  | 'office'
  | 'presentation'
  | 'diagram'
  | 'ui-ux'
  | 'visual-design'
  | 'image'
  | 'video'
  | 'accessibility'
  | 'drafting'
  | 'translation'
  | 'editing'
  | 'seo'
  | 'social-media'
  | 'advertising'
  | 'sales'
  | 'ecommerce'
  | 'communication'
  | 'notes-calendar'
  | 'project-management'
  | 'automation'
  | 'learning'
  | 'web-research'
  | 'academic'
  | 'market-research'
  | 'security-review'
  | 'vulnerability'
  | 'auth'
  | 'skill-authoring'
  | 'mcp'
  | 'agent-operations'
  | 'ai-engineering'
  | 'persona'
  | 'finance'
  | 'legal'
  | 'health'
  | 'business-ops'
  | 'audio'
  | 'lifestyle'
  | 'misc'
  | 'investing'
  | 'financial-analysis'
  | 'accounting-tax'
  | 'speech'
  | 'music'
  | 'sound'
  | 'contracts'
  | 'compliance'
  | 'legal-work';

export type ScriptFiles = 'none' | 'present' | 'unknown';

export interface SiteSkill {
  slug: string;
  rank: number;
  name: string;
  repository: string;
  path: string;
  license: string | null;
  firstSeenAt: string;
  summary: string;
  useWhen: string;
  category: Category;
  /** v6 이전 요약에는 없다. */
  subcategory: Subcategory | null;
  tags: { roles: Role[]; useCases: string[]; difficulty: Difficulty };
  runsExternalCode: boolean;
  accessesNetwork: boolean;
  requiresExternalAccount: boolean;
  /** 스킬 폴더의 파일 목록으로 정한 사실이다. unknown은 저장소 루트 스킬이거나 목록이 잘린 경우다. */
  scriptFiles: ScriptFiles;
  promptVersion: string;
}

export interface SiteData {
  schemaVersion: number;
  bootstrappedOn: string | null;
  repositories: SiteRepository[];
  skills: SiteSkill[];
}

export interface Skill extends SiteSkill {
  stars: number;
  pushedAt: string;
  defaultBranch: string;
}
