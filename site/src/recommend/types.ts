/** 자연어 추천의 경계. 임베딩 검색으로 바꿀 때는 Recommender 구현만 교체한다. */

export interface CatalogEntry {
  slug: string;
  name: string;
  summary: string;
}

export interface Suggestion {
  slug: string;
  reason: string;
}

export interface Recommender {
  recommend(question: string, catalog: CatalogEntry[]): Promise<Suggestion[]>;
}

/** Workers KV 중 이 기능이 쓰는 부분만 정의해 테스트에서 메모리로 대체한다. */
export interface KeyValueStore {
  get(key: string): Promise<string | null>;
  put(key: string, value: string, options: { expirationTtl: number }): Promise<void>;
}
