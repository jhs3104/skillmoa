import type { CatalogItem } from './catalog';
import { CATEGORY_LABELS, formatDate, formatStars, STAR_PATH, SUBCATEGORY_LABELS } from './labels';

export interface RowOptions {
  dateKind?: 'updated' | 'found';
  reason?: string;
  query?: string;
}

const ENTITIES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (character) => ENTITIES[character]!);
}

function badge(label: string, title?: string): string {
  const hint = title ? ` title="${title}"` : '';
  return `<span class="badge badge--caution"${hint}>${label}</span>`;
}

/** 목록 행의 유일한 원본이다. 서버 출력과 브라우저 렌더링이 같은 함수를 쓴다. */
export function skillRowHtml(item: CatalogItem, { dateKind = 'updated', reason, query = '' }: RowOptions = {}): string {
  const date = dateKind === 'found' ? item.firstSeenAt : item.pushedAt;
  const dateLabel = dateKind === 'found' ? '발견일' : '업데이트';
  const href = `/skills/${encodeURIComponent(item.slug)}/${query}`;
  const blocked = item.installBlocked ? badge('설치 명령 없음') : '';
  /** 코드 실행·네트워크는 10개 중 8개에 붙어 목록에서 구별되지 않는다. 유료일 수 있다는 신호만 목록에 둔다 (ADR-0019). */
  const account = item.requiresExternalAccount ? badge('계정·API 키 필요', 'AI가 SKILL.md를 읽고 찾은 내용입니다. 유료 서비스일 수 있습니다.') : '';
  const why = reason ? `<p class="skill__reason">${escapeHtml(reason)}</p>` : '';
  const sub = item.subcategory ? `<span class="skill__sub">${SUBCATEGORY_LABELS[item.subcategory]}</span>` : '';
  return `<li class="skill" data-id="${escapeHtml(item.slug)}">
  <span class="cat-label" data-cat="${item.category}">${CATEGORY_LABELS[item.category]}</span>
  <div class="skill__body">
    <div class="skill__title">
      <h3 class="skill__name"><a href="${escapeHtml(href)}">${escapeHtml(item.name)}</a></h3>${sub}
      <span class="skill__repo">${escapeHtml(item.repository)}</span>${blocked}${account}
    </div>${why}
    <p class="skill__summary">${escapeHtml(item.summary)}</p>
    <p class="skill__when">${escapeHtml(item.useWhen)}</p>
  </div>
  <div class="skill__meta">
    <span class="stat stat--updated"><span class="stat__label">${dateLabel} </span>${formatDate(date)}</span>
    <span class="stat stat--stars"><span class="visually-hidden">저장소 스타 </span><svg class="star" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="${STAR_PATH}" /></svg>${formatStars(item.stars)}</span>
  </div>
</li>`;
}
