# ADR-0001: 상시 서버 없이 GitHub Actions와 Cloudflare Workers로 구성한다

- 상태: 채택
- 날짜: 2026-11-01

## 맥락

사이트는 매일 바뀌는 카탈로그를 보여주지만, 대부분의 요청은 읽기다. 개인 프로젝트라 운영 시간과 고정비를 최소로 유지해야 하고, 쓰기가 필요한 기능은 자연어 추천의 요청 제한과 캐시뿐이다.

초기 계획은 Cloudflare Pages Git 연동이었다. 구현 시작 시점에 확인한 결과 `@astrojs/cloudflare`의 현재 문서는 "no longer supports deployment on Cloudflare Pages"라고 명시하고 Workers 이전을 안내한다.

## 결정

- 배치는 GitHub Actions에서 실행한다.
- 사이트는 Astro로 만들고 `@astrojs/cloudflare`로 Cloudflare Workers(정적 자산 포함)에 배포한다.
- 페이지는 기본 정적으로 생성하고, 동적 기능은 `prerender = false`인 Astro 엔드포인트로만 만든다.
- 영속 데이터는 Git 저장소의 JSON과 Workers KV만 쓴다. 상시 서버와 RDB는 두지 않는다.
- 배포는 Workers Builds Git 연동을 쓴다. Root directory는 `site`다.

## 검토한 대안

| 대안 | 장점 | 기각 이유 |
|---|---|---|
| 구버전 어댑터로 Pages 유지 | 초기 계획과 동일 | 지원이 끝난 경로에 새 프로젝트를 고정하게 된다 |
| 정적 사이트만 Pages, API는 별도 Worker | Pages 유지 가능 | 배포 단위가 둘로 늘고 어댑터의 이점을 잃는다 |
| VPS + DB | 쿼리와 전문 검색이 자유롭다 | 고정비와 운영 부담이 규모에 비해 크다 |

## 결과

- 무료 플랜의 Worker 버전당 정적 자산은 2만 개, 파일당 25MiB, 요청은 하루 10만 건이다. 정적 생성은 상위 스킬로 제한하고, 넘어서는 범위는 D1 + 온디맨드 렌더링으로 옮긴다.
- Workers KV 무료 쓰기는 하루 1,000건이다. 추천 API는 이 한도 안에서 설계한다.
- 동적 기능의 런타임은 Workers로 고정된다. Node 전용 라이브러리는 쓸 수 없다.
- Astro는 6.x를 쓴다. 7.x는 Node 22.23.4 이상이 필요한데 개발 환경이 22.17.0이다. Node를 올리면 Astro 7과 어댑터 14로 올릴 수 있다.
- 나중에 전문 검색이나 사용자별 데이터가 필요해지면 D1 도입을 다시 검토한다.
