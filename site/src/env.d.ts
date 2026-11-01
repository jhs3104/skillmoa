/// <reference types="astro/client" />

interface ImportMetaEnv {
  readonly PUBLIC_USE_SAMPLE_DATA?: string;
  readonly PUBLIC_ADS_ENABLED?: string;
}

declare module 'cloudflare:workers' {
  export const env: {
    ANTHROPIC_API_KEY?: string;
    ANTHROPIC_BASE_URL?: string;
    RECOMMEND_MODEL?: string;
    RECOMMEND_KV?: import('./recommend/types').KeyValueStore;
    ASSETS: { fetch(input: string | URL | Request): Promise<Response> };
  };
}
