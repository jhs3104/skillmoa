---
name: run-collector-small
description: 로컬에서 수집·요약 파이프라인을 소규모로 검증한다. collector나 요약 프롬프트를 바꾼 뒤, 또는 새 소스를 추가한 뒤 실제 실행 결과를 확인할 때 사용한다.
---

# 소규모 collector 검증

`collector/`에서 실행한다. 규모는 기본 10개, 최대 20개다. 전체 수집은 GitHub Actions에서만 돌린다.

## 절차

1. `uv run python -m collector --help`로 실제 옵션을 확인한다. `--limit`이 없으면 구현이 먼저 필요하다고 보고하고 멈춘다.
2. `[ -n "${ANTHROPIC_API_KEY:-}" ]`로 API 키 유무만 확인한다. 값은 출력하지 않고, `.env`는 열지 않는다.
3. collector를 실행한다.
   - 키가 있으면: `uv run python -m collector --limit N`
   - 키가 없으면: `uv run python -m collector --limit N --mock-summary` (요약 단계만 mock)
4. `collector/build/samples/`에 스킬마다 아래 파일이 있는지 확인한다.
   - `<owner>__<repo>__<skill>/source.md`: 원문 SKILL.md
   - `<owner>__<repo>__<skill>/summary.json`: 생성된 요약
5. 실행 결과를 요약한다.
   - 처리한 스킬 수, 소요 시간, 입력·출력 토큰 사용량 (mock이면 mock이라고 명시)
   - 필터 제외 사유별 개수
6. 이상 징후의 원인을 분석한다. 이상 징후는 오류, 샘플 누락, 토큰 급증, 한 사유로 제외가 몰리는 경우, 비어 있거나 원문과 어긋난 요약이다.

스킬마다 샘플 쌍이 있거나 빠진 이유가 설명되고, 모든 이상 징후에 원인 또는 확인할 다음 단계가 적혀 있으면 완료다.

mock 샘플은 실제 요약이 아니므로 `summary-reviewer` 검증 대상에서 뺀다.
