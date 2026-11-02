import type { APIRoute } from 'astro';
import { jsonFile, toCatalogItem } from '../lib/catalog';
import { skills } from '../lib/data';

/** 목록과 맞춤 추천이 브라우저에서 필요할 때 읽는 전체 목록. */
export const GET: APIRoute = () => jsonFile(skills.map(toCatalogItem));
