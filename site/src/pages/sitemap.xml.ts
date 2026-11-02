import type { APIRoute } from 'astro';
import { skills } from '../lib/data';
import { isIndexable } from '../lib/seo';

/** 색인 대상만 싣는다. noindex 페이지는 사이트맵에 넣지 않는다. */
export const GET: APIRoute = ({ site }) => {
  const paths = ['/', '/new/', '/recommend/', '/ask/'];
  paths.push(...skills.filter(isIndexable).map((skill) => `/skills/${skill.slug}/`));
  const entries = paths
    .map((path) => `  <url><loc>${new URL(path, site).href}</loc></url>`)
    .join('\n');
  const body = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${entries}
</urlset>
`;
  return new Response(body, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
};
