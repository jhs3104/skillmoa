/** skills.schema.json과 같은 계약이다. 스키마를 바꾸면 함께 바꾼다. */

export type Category =
  | 'development' | 'testing' | 'devops' | 'data' | 'documents' | 'design' | 'writing'
  | 'marketing' | 'productivity' | 'research' | 'security' | 'ai-agents' | 'other';

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
  tags: { roles: Role[]; useCases: string[]; difficulty: Difficulty };
  runsExternalCode: boolean;
  accessesNetwork: boolean;
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
