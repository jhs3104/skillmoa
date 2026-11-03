import type { CatalogItem } from './catalog';
import { CATEGORY_LABELS, formatDate, formatStars, STAR_PATH } from './labels';

export interface RowOptions {
  dateKind?: 'updated' | 'found';
  reason?: string;
  query?: string;
}

const ENTITIES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (character) => ENTITIES[character]!);
}

function badge(label: string, tone: 'caution' | 'quiet' = 'caution'): string {
  return `<span class="badge badge--${tone}">${label}</span>`;
}

/** AI가 코드 실행·네트워크를 찾지 못한 스킬은 폴더의 파일로 한 번 더 나눈다. */
function quietBadge(item: CatalogItem): string {
  if (item.runsExternalCode || item.accessesNetwork) return '';
  if (item.scriptFiles === 'none') return badge('지침 문서만', 'quiet');
  if (item.scriptFiles === 'present') return badge('스크립트 포함');
  return badge('코드·네트워크 미확인', 'quiet');
}

function flags(item: CatalogItem): string {
  return [
    item.runsExternalCode ? badge('코드 실행') : '',
    item.accessesNetwork ? badge('네트워크') : '',
    item.requiresExternalAccount ? badge('외부 계정 필요') : '',
    quietBadge(item),
  ].join('');
}

/** 목록 행의 유일한 원본이다. 서버 출력과 브라우저 렌더링이 같은 함수를 쓴다. */
export function skillRowHtml(item: CatalogItem, { dateKind = 'updated', reason, query = '' }: RowOptions = {}): string {
  const date = dateKind === 'found' ? item.firstSeenAt : item.pushedAt;
  const dateLabel = dateKind === 'found' ? '발견일' : '업데이트';
  const href = `/skills/${encodeURIComponent(item.slug)}/${query}`;
  const blocked = item.installBlocked ? badge('설치 명령 없음') : '';
  const why = reason ? `<p class="skill__reason">${escapeHtml(reason)}</p>` : '';
  return `<li class="skill" data-id="${escapeHtml(item.slug)}">
  <span class="cat-label" data-cat="${item.category}">${CATEGORY_LABELS[item.category]}</span>
  <div class="skill__body">
    <div class="skill__title">
      <h3 class="skill__name"><a href="${escapeHtml(href)}">${escapeHtml(item.name)}</a></h3>
      <span class="skill__repo">${escapeHtml(item.repository)}</span>${blocked}
    </div>${why}
    <p class="skill__summary">${escapeHtml(item.summary)}</p>
    <p class="skill__when">${escapeHtml(item.useWhen)}</p>
  </div>
  <div class="skill__meta">
    <span class="skill__flags">${flags(item)}</span>
    <span class="stat stat--updated"><span class="stat__label">${dateLabel} </span>${formatDate(date)}</span>
    <span class="stat stat--stars"><span class="visually-hidden">저장소 스타 </span><svg class="star" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="${STAR_PATH}" /></svg>${formatStars(item.stars)}</span>
  </div>
</li>`;
}
