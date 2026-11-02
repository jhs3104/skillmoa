---
version: 1
slug: "site-src-pages-index-astro"
primary_target: "site/src/pages/index.astro"
related_targets: ["site/src/pages/skills/[slug].astro","site/src/pages/recommend/index.astro","site/src/pages/ask/index.astro"]
---

# 스킬모아 홈·상세

Mode: Operate (홈, 추천), Read (상세 위쪽).
사용자 지시: claudeskills.info는 느낌의 참고일 뿐이고 화면이 같아 보이면 안 된다. 목록으로 보여 주고, 들어가면 어떤 스킬인지 요약하고 GitHub로 연결하며, AI로 원하는 스킬도 찾아 준다. AI 찾기는 맨 처음에 두면 사용자가 그것부터 쓰게 되므로 따로 뺀다. 이전 초록 띠 디자인은 올드해 보인다는 피드백으로 폐기했다. 왼쪽 상단 글자 이름은 넣지 않는다.

## Direction contract

THESIS: 카테고리 색 라벨을 훑으면 어떤 스킬인지 보인다. 초록 띠, 종이색 바탕, 테두리 상자를 버린다.

OWN-WORLD: 순백 바탕, 거의 검은 글자, 코발트 강조, 카테고리마다 선명한 단색 라벨, 아주 굵은 큰 한글 제목, 테두리 없는 가라앉은 회색 입력칸, 얇은 선으로만 나눈 목록. 앰버는 주의에만 쓴다. Pretendard.

STORY: 방문자는 라벨 색으로 목록을 훑거나 키워드로 좁히고, 찾지 못하면 AI 찾기에 묻는다. 상세에서 요약을 읽고 판단 근거를 본 뒤 설치하거나 GitHub로 간다.

FIRST VIEWPORT: 맨 위 메뉴(현재 메뉴는 코발트 알약). 왼쪽에 52px 굵은 제목과 소개, 오른쪽에 큰 검색칸. 그 아래 전폭 색 라벨 필터, 결과 줄, 큰 순위 숫자와 카테고리 라벨이 붙은 목록.

FORM: 잔여 후보 중 추첨으로 정한 컬러 인덱스 라벨, 목록 6번째. seed:fba232aba5a94efb

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
