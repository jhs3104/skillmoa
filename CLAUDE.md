# 한국어 AI 에이전트 스킬 디렉터리

Claude Code / Codex / Cursor 등에서 쓰는 SKILL.md 기반 스킬을 한국어로 정리·추천하는 사이트.

- 최종 목표: GitHub의 모든 스킬 + 매일 신규 스킬 수집. 첫 출시는 상위 300개.
- 이직 포트폴리오 용도도 있으므로 설계 결정과 트레이드오프를 `docs/adr/`에 남긴다.

**이 파일의 작업 방식이 설치된 플러그인의 워크플로보다 우선한다.**

## 작업 방식

- 단계가 끝날 때 검증한다: collector는 `uv run pytest`, site는 `npm run check`.
- 커밋까지만 한다. 원격 반영은 사용자가 직접 한다 (`git push` 금지).
- 요약 프롬프트를 바꾸면 `summary-reviewer` 에이전트로 검증한다.
- `uv` 명령은 `collector/`에서, `npm`·`npx` 명령은 `site/`에서 실행한다.

## 구조

모노레포다.

- `collector/`: Python 3.12+ 배치. uv로 패키지·가상환경 관리 (`pyproject.toml`). 코드는 `src/collector/`, 테스트는 `tests/`
  - 라이브러리: httpx(HTTP), tenacity(재시도), pydantic(스키마·검증), anthropic(공식 SDK), pytest, ruff
  - `src/collector/domain/`: 모델·규칙. 외부 의존 없음
  - `src/collector/sources/`: GitHub·awesome 리스트 등 어댑터
  - `src/collector/pipeline/`: 수집·필터·요약 흐름
  - `src/collector/summarize/`: Claude API
  - `src/collector/export/`: JSON 출력
  - 흐름: 수집 → 품질 필터 → Claude API 한국어 요약 → `site/src/data/skills.json` export
  - 수집 상태(알려진 저장소, pushed_at, SKILL.md 해시, 프롬프트 버전)는 `collector/state/`에 JSON으로 저장하고
    `skills.json`과 함께 커밋한다. GitHub Actions는 실행마다 환경이 초기화되기 때문이다.
- `site/`: Astro + `@astrojs/cloudflare` 어댑터
  - 페이지는 기본 정적(prerender)
  - 동적 기능은 Astro 엔드포인트(`src/pages/api/*`, `prerender=false`)로만 만든다.
  - Astro 6.x를 쓴다. 7.x는 Node 22.23.4 이상이 필요하다 (ADR-0001).
- `.github/workflows/`: collector 일일 실행 → JSON 커밋 → Cloudflare 자동 재배포
- `docs/data-flow.md`: 파이프라인 흐름과 파일별 소유자
- `docs/adr/`: 설계 결정 기록

## 인프라

- 서버 없음 원칙: 상시 서버·DB를 두지 않는다. 배치는 GitHub Actions, 동적 기능은 Cloudflare에서만 실행한다.
- 배포: Cloudflare Workers Builds Git 연동 (Root directory: `site` / Build: `npm run build` / Deploy: `npx wrangler deploy`). `@astrojs/cloudflare`가 Pages 지원을 중단했다 (ADR-0001).
- 무료 플랜은 Worker 버전당 정적 파일 2만 개 제한이 있다. 정적 생성은 상위 스킬만 하고, 나머지는 나중에 D1 + 온디맨드 렌더링으로 처리한다.

## 도메인 모델

- `Repository`(owner/name, 스타, pushed_at, 라이선스) 1:N `Skill`(경로, SKILL.md 해시, firstSeenAt, lastSeenAt)
- 스타는 저장소 단위이므로 정렬 시 저장소당 노출 상한을 고려한다.

## 코드 원칙

- 타입 힌트 필수.
- 외부 호출은 `sources/`·`summarize/`에만 둔다.
- `domain/`은 순수 함수 위주로 테스트한다.

## 비밀값

- GitHub 검색용 토큰은 `GH_SEARCH_TOKEN`. GitHub Secrets 이름은 `GITHUB_`로 시작할 수 없다. fine-grained PAT, 공개 저장소 읽기만 허용한다.
- `ANTHROPIC_API_KEY`는 GitHub Secrets / Cloudflare 환경변수(secret)에만 둔다.
- 비밀값은 환경변수로만 읽는다. 코드·프론트에 하드코딩 금지. `.env`는 읽지 말 것.

## Claude API

- 요약은 Haiku 계열 저가 모델을 쓴다. 모델 ID는 설정값으로 둔다 (하드코딩 금지).
- 재시도·타임아웃·일일 호출 상한 필수.
- SKILL.md 해시가 바뀐 스킬만 재요약한다.
- 프롬프트는 버전 관리하고, 레코드에 프롬프트 버전을 저장한다.

## 콘텐츠

- 요약은 새로 쓴 설명이어야 한다. 원문 번역·복사 금지.
- 원본 링크·라이선스를 항상 표시한다.
- SEO: 기준(스타 N개 이상 또는 수동 검수) 이상만 index, 나머지는 noindex. 사이트맵에는 index 대상만 넣는다.

## 환경

- M1 8GB 맥북. 로컬은 스킬 10~20개 규모로만 테스트하고, 전체 수집은 GitHub Actions에서 실행한다.
- dev 서버는 하나만 띄운다.
- 시스템 `python3`는 3.8이다. collector는 항상 `uv run`으로 실행한다.

## 디자인

impeccable 스킬을 사용한다 (하네스 세팅 후 별도 설치). 다른 frontend-design 스킬과 섞지 않는다.

- UI 작업 시작 전 `/teach-impeccable`이 아직 안 됐으면 먼저 실행을 제안한다.
- UI 단계마다 구현 → `/audit` → `/critique` → 수정 → `/polish` 순서로 진행하고, 결과를 요약해서 보고한다.
- 모바일 우선, 한국어 가독성 우선. 본문 폰트는 Pretendard 등 한글 웹폰트를 셀프 호스팅한다.
- 템플릿 같은 기본 디자인 금지. 광고 영역은 콘텐츠를 가리지 않는 위치에 미리 자리를 잡아둔다.
- 디자인 방향: 둘러보기 쉬운 정보 밀도. 카드/표 전환 가능.
  - 스타 수·업데이트일·외부 실행 여부 배지를 한눈에 보여준다.
  - 필터는 모바일에서 하단 시트로 연다.
  - 맞춤 추천 질문 흐름은 `/onboard`, 문구는 `/clarify`로 점검한다.
