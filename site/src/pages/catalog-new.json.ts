import type { APIRoute } from 'astro';
import { jsonFile, toCatalogItem } from '../lib/catalog';
import { freshSkills } from '../lib/data';

/** 새 스킬 페이지가 읽는 목록. */
export const GET: APIRoute = () => jsonFile(freshSkills().map(toCatalogItem));
