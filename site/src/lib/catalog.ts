import type { Category, Difficulty, Role } from './types';

export interface CatalogItem {
  slug: string;
  name: string;
  summary: string;
  useWhen: string;
  category: Category;
  roles: Role[];
  difficulty: Difficulty;
  rank: number;
}
