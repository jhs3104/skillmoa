import type { CatalogItem } from '../lib/catalog';

const requests = new Map<string, Promise<CatalogItem[]>>();

/** 같은 목록은 한 번만 받는다. 실패하면 다시 시도할 수 있게 비운다. */
export function loadCatalog(url = '/catalog.json'): Promise<CatalogItem[]> {
  let request = requests.get(url);
  if (!request) {
    request = fetch(url)
      .then((response) => {
        if (!response.ok) throw new Error(`catalog: ${response.status}`);
        return response.json() as Promise<CatalogItem[]>;
      })
      .catch((error: unknown) => {
        requests.delete(url);
        throw error;
      });
    requests.set(url, request);
  }
  return request;
}
