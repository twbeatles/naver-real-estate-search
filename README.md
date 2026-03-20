# naver-real-estate-search

네이버 부동산 기반으로 대한민국 **매물 검색 / 단지 후보 탐색 / 비교 브리핑 / 가격 감시**를 수행하는 OpenClaw 스킬입니다.

이 저장소는 자연어 질의(`잠실 리센츠 전세 30평대`, `은마와 래미안대치팰리스 비교`, `신월시영아파트 후보부터 보여줘`)를 받아, **후보 단지 좁히기 → 단일 단지 조회 → 비교 요약 → watch rule 저장**까지 이어지는 실사용 중심 흐름을 제공합니다.

특히 한국어 부동산 질의에서 자주 문제 되는 아래를 보강했습니다.

- 단지명 축약/별칭 처리
- cold-start 후보 탐색 품질 개선
- direct complex ID / URL 우선 흐름
- 동일 평형 기준 비교 요약
- 새 매물 / 가격 하락 감지용 watch schema
- 텔레그램/브리핑 레이어에 붙이기 쉬운 stdout JSON 구조

---

## What this skill is good at

이 스킬은 아래 같은 요청에 특히 잘 맞습니다.

- `강남 아파트 전세 시세 찾아줘`
- `잠실 리센츠 전세 30평대 요약해줘`
- `리센츠와 엘스 전세 비교해줘`
- `신월시영아파트 후보부터 찾아줘`
- `목표가 이하 매물 나오면 체크해줘`
- `새 매물이나 가격 하락만 감시해줘`

핵심 장점은 다음과 같습니다.

- 자연어 질의를 그대로 받을 수 있음
- direct complex ID / URL이 있으면 더 안정적으로 조회 가능
- 후보 단지를 1~3개 수준으로 좁혀서 rate limit과 오탐을 줄임
- 단순 raw 데이터가 아니라 한국어 비교 브리핑을 바로 제공함
- watch rule 저장 후 반복 점검 흐름을 붙이기 쉬움

---

## Current feature set

현재 README 기준 핵심 기능:

- 자연어 기반 단지/매물 검색
- 후보 단지 탐색 (`--list-candidates`)
- 단일 단지 조회
- 여러 단지 비교 (`--compare`)
- 동일 평형 기준 비교 요약
- 단지 alias / 주소 / ID candidate cache
- 운영 seed / generated seed 분리 관리
- candidate seed 자동 생성 및 승격 preview/apply
- 채팅형 브리핑 래퍼
- 가격 감시 / 새 매물 / 가격 하락 감지
- stdout JSON 구조화 출력

---

## Repository layout

```text
naver-real-estate-search/
├── README.md
├── SKILL.md
├── data/
│   ├── candidate-cache.json
│   └── watch-rules.json
├── references/
│   ├── candidate-seed-builder.md
│   ├── candidate-seeds.generated.json
│   ├── candidate-seeds.json
│   ├── design.md
│   └── seoul-major-complexes.seed-input.json
└── scripts/
    ├── apply_generated_seeds.py
    ├── build_candidate_seeds.py
    ├── chat_real_estate.py
    ├── search_real_estate.py
    └── watch_real_estate.py
```

---

## Environment / requirements

실사용 전 전제 조건:

- Python 실행 환경
- 네이버 부동산 접근이 가능한 네트워크 환경
- 반복 조회 결과를 저장할 로컬 파일 시스템
- rate limit/429 상황을 감안한 운영 방식

이 스킬은 broad crawling보다는 **필요한 단지 후보를 좁혀서 조회하는 방식**이 더 안정적입니다. direct complex URL 또는 complex ID를 확보할 수 있으면 그 경로를 우선 쓰는 편이 좋습니다.

현재 GitHub homepage는 upstream/source 저장소인 [`twbeatles/naverland-scrapper`](https://github.com/twbeatles/naverland-scrapper)를 가리키며, 이 스킬은 그 로직을 OpenClaw용 워크플로로 감싼 래퍼 성격이 강합니다.

---

## Recommended workflow

실전에서는 아래 흐름을 가장 추천합니다.

1. **URL/complex ID가 있으면 먼저 사용**한다.
2. 없으면 `chat_real_estate.py --query ...`로 자연어 브리핑을 먼저 본다.
3. 질의가 넓거나 애매하면 `--list-candidates`로 후보를 1~3개만 좁힌다.
4. 후보가 정리되면 `--compare` 또는 단일 단지 조회로 넘어간다.
5. 반복 확인이 필요하면 `watch_real_estate.py add/check`를 붙인다.
6. 상위 서비스가 후처리해야 하면 동일 질의를 `--json`으로 다시 호출한다.

이 흐름이 좋은 이유는, 너무 넓은 스캔보다 **의미 있는 후보를 좁힌 뒤 조회하는 방식**이 정확도와 안정성 모두에서 유리하기 때문입니다.

---

## Quick start

### 1) 자연어 단일 검색

```bash
python scripts/search_real_estate.py --query "잠실 리센츠 전세 30평대"
```

### 2) 자연어 비교 검색

```bash
python scripts/search_real_estate.py --query "잠실 리센츠와 엘스 전세 비교 30평대" --compare --json
```

### 3) 후보 단지만 먼저 보기

```bash
python scripts/search_real_estate.py --query "서울 양천구 신월동 신월시영아파트 전세" --list-candidates --json
```

### 4) 채팅형 브리핑

```bash
python scripts/chat_real_estate.py --query "잠실 리센츠 전세 30평대"
```

### 5) complex ID 직접 조회

```bash
python scripts/search_real_estate.py --complex-id 1147 --trade-types 전세 --limit 10
```

### 6) direct URL 직접 조회

```bash
python scripts/search_real_estate.py --url "https://new.land.naver.com/complexes/1147" --trade-types 매매,전세 --json
```

---

## CLI overview

### `scripts/search_real_estate.py`

핵심 검색 엔진입니다.

주요 옵션:

- `--query`: 자연어 또는 지역/단지 키워드
- `--complex-id`: 네이버 부동산 단지 ID 직접 지정
- `--url`: 네이버 부동산 단지/매물 URL 직접 지정
- `--trade-types`: `매매`, `전세`, `월세` 등 쉼표 구분 거래 유형
- `--pages`, `--limit`: 조회 범위 제어
- `--candidate-limit`: 후보 단지 개수 제한
- `--min-pyeong`, `--max-pyeong`: 평형대 필터
- `--list-candidates`: 후보 단지만 출력
- `--compare`: 후보 상위 단지 비교 조회
- `--parse-only`: 자연어 파싱 결과만 확인
- `--show-cache`: candidate cache 조회
- `--seed-candidate-file`: seed 파일을 candidate-cache에 반영
- `--seed-candidate`: 단일 후보를 직접 cache에 저장
- `--json`: 구조화 결과 출력
- `--self-test`: 셀프 테스트

### `scripts/chat_real_estate.py`

사람이 읽기 쉬운 한국어 브리핑 래퍼입니다.

좋은 사용처:

- 텔레그램/챗봇 답변
- 후보 단지 비교 요약
- 매물 리스트보다 해석이 더 중요한 상황

### `scripts/watch_real_estate.py`

가격 감시 / 새 매물 감지 스크립트입니다.

서브커맨드:

- `add`: 감시 규칙 추가
- `list`: 저장 규칙 목록 조회
- `check`: 저장 규칙 점검

---

## Practical examples

### 자연어 파싱 결과만 먼저 확인

```bash
python scripts/search_real_estate.py --query "잠실 리센츠랑 엘스 전세 비교 30평대" --parse-only
```

### 후보 리스트를 채팅형으로 보기

```bash
python scripts/chat_real_estate.py --query "대치 은마 전세" --list-candidates
```

### 여러 단지 비교 브리핑

```bash
python scripts/chat_real_estate.py --query "잠실 리센츠와 잠실 엘스 전세 비교 30평대" --compare --candidate-limit 2
```

### 평형대 필터와 함께 조회

```bash
python scripts/search_real_estate.py --query "잠실 리센츠 전세" --min-pyeong 30 --max-pyeong 34 --json
```

---

## Candidate discovery strategy

후보 단지 탐색은 대략 다음 순서로 동작합니다.

1. direct complex ID / URL 우선 추출
2. 자연어에서 위치 힌트 / 거래 유형 / 평형대 / 비교 대상 분리
3. 로컬 candidate cache(alias → complex_id) exact/contains 매칭
4. 캐시에 없으면 네이버 검색 결과에서 후보 complex ID 수집
5. 가능하면 단지 상세 정보로 이름/주소/세대수 보강
6. 이름 정규화 / alias / 위치 힌트 / 질의 토큰 / 세대수 기반 점수화
7. 상위 후보만 반환

실전 팁:

- `신월시영아파트`, `목동신시가지7단지`처럼 alias가 흔들리는 단지는 **먼저 후보를 보고 확정**하는 쪽이 안전합니다.
- broad scan보다 **후보 1~3개를 먼저 좁히는 방식**이 rate limit과 오탐을 줄입니다.
- complex ID를 한 번 확보한 단지는 cache에 학습시켜 두는 편이 좋습니다.

---

## Candidate cache / seed workflow

이 저장소는 **운영 seed**와 **자동 생성 초안**을 분리합니다.

### 1) generated seed 초안 만들기

```bash
python scripts/build_candidate_seeds.py --print-summary
python scripts/build_candidate_seeds.py --input references/seoul-major-complexes.seed-input.json --output references/candidate-seeds.generated.json --pause 0.1 --print-summary
```

생성 결과에는 아래 같은 메타가 들어갑니다.

- `confidence`
- `verification_status`
- `aliases`
- `candidate_pool`
- `evidence`
- `blocked_reasons`

중요한 점: 이 파일은 **운영 투입본이 아니라 generated 초안**입니다.

### 2) preview로 승격 후보 확인

```bash
python scripts/apply_generated_seeds.py --json
python scripts/apply_generated_seeds.py --only-names "리센츠,은마" --json
```

기본 동작은 preview이며 파일을 직접 바꾸지 않습니다.

### 3) 실제 반영

```bash
python scripts/apply_generated_seeds.py --apply-target --apply-cache --json
```

- `--apply-target`: `references/candidate-seeds.json` 갱신
- `--apply-cache`: accepted 항목만 `data/candidate-cache.json`에 반영

추천 습관:

1. generated 생성
2. preview 확인
3. accepted / manual review 구분 검토
4. 문제 없을 때만 apply

---

## Manual seeding / cache learning

반복 조회가 많은 단지는 cache를 수동 보강해두면 편합니다.

### 운영 seed 전체 반영

```bash
python scripts/search_real_estate.py --seed-candidate-file
```

### 단일 후보 수동 저장

```bash
python scripts/search_real_estate.py --seed-candidate --complex-id 1147 --candidate-name "리센츠" --candidate-address "서울특별시 송파구 잠실동" --candidate-aliases "잠실 리센츠,잠실리센츠"
```

### cache 확인

```bash
python scripts/search_real_estate.py --show-cache --query "리센츠"
```

이 기능은 특히 아래 케이스에서 유용합니다.

- 자주 물어보는 대표 단지
- 공백/축약 차이가 큰 단지명
- complex ID를 이미 알고 있는 단지
- cold-start 탐색 실패를 줄이고 싶은 경우

---

## Watch rules

### 1) 감시 규칙 추가

```bash
python scripts/watch_real_estate.py add --name "리센츠 전세 30평대" --query "잠실 리센츠 전세 30평대" --target-max-price 950000000 --notify-on-new --notify-on-price-drop
```

### 2) 규칙 목록 확인

```bash
python scripts/watch_real_estate.py list
```

### 3) 점검 미리보기

```bash
python scripts/watch_real_estate.py check --preview
```

### 4) JSON 결과로 점검

```bash
python scripts/watch_real_estate.py check --json
```

watch rule은 다음 정보와 잘 결합됩니다.

- `last_seen`
- `events`
- dedupe 기반 이벤트 기록
- 새 매물 감지
- 가격 하락 감지

즉, 텔레그램/브리핑 상위 레이어가 `message_preview`나 `summary`만 써도 되고, 더 정밀하게는 `alerts` / `events` / `snapshot` 계층을 직접 가공해도 됩니다.

---

## Output style

이 스킬은 raw scraping 결과를 그대로 노출하기보다, 아래 순서의 결과를 지향합니다.

### 단일 단지

- 단지명 / 위치
- 필터 요약
- 건수 / 최저가 / 평균가 / 중앙값 / 최고가
- 대표 동일 평형 요약
- 대표 매물 2~3개
- 사람이 읽기 쉬운 짧은 해석

### 여러 단지 비교

- 단지별 핵심 수치
- 어느 단지가 평균 기준 더 낮은지
- 가능하면 동일 평형 기준 차이
- 대표 매물/링크

### 감시 결과

- rule 이름 / id
- 목표가 이하 매물 수
- 신규 매물 / 가격 하락 이벤트
- preview 또는 JSON 둘 다 사용 가능

---

## Limitations / operational notes

실사용 시 알아둘 점:

- 429 / 차단 상황에서는 broad scan보다 direct URL/ID 흐름이 낫습니다.
- generated seed는 자동화 초안일 뿐, 운영 승격 전 검수가 필요합니다.
- alias가 흔한 단지는 오탐 가능성이 있어 manual review가 중요합니다.
- 네이버 부동산 구조 변화가 있으면 후보 탐색/정규화 로직도 조정이 필요할 수 있습니다.
- 전국 단위 대규모 일괄 스캔보다는, 질문 의도에 맞는 좁은 후보 탐색에 최적화돼 있습니다.

---

## Deployment / release notes

현재 GitHub 최신 릴리스: **v0.6.2**

배포 전 확인하면 좋은 흐름:

1. `search_real_estate.py --self-test`
2. 대표 자연어 질의 테스트
3. `--list-candidates` / `--compare` 케이스 점검
4. watch add/check 흐름 점검
5. `references/candidate-seeds.json`와 `manual_review_queue` 상태 확인
6. 태그/릴리스 생성 후 배포 채널 동기화

최근 버전 흐름을 크게 요약하면:

- `v0.2.x`: 기본 OpenClaw 부동산 검색/브리핑 구조 정리
- `v0.4.x~v0.5.x`: 후보 탐색, 비교, watch schema 실사용성 강화
- `v0.6.x`: candidate seed 자동 생성/preview/apply, alias 관리, 운영 검수 흐름 강화

---

## Related references

세부 설계나 seed 운영 기준은 아래 파일을 함께 보면 좋습니다.

- `references/design.md`
- `references/candidate-seed-builder.md`
- `references/candidate-seeds.json`
- `references/candidate-seeds.generated.json`
- `references/seoul-major-complexes.seed-input.json`

GitHub Releases: <https://github.com/twbeatles/naver-real-estate-search/releases>

