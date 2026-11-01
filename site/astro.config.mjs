import cloudflare from '@astrojs/cloudflare';
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: process.env.SITE_URL ?? 'https://skill-directory.workers.dev',
  output: 'static',
  adapter: cloudflare({ imageService: 'passthrough' }),
  trailingSlash: 'always',
});
