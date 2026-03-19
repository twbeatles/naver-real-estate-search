---
name: naver-real-estate-search
description: Search 네이버 부동산 listings and 단지 candidates for 대한민국 real-estate requests such as 강남 아파트 전세 시세 찾기, 특정 지역 매매/전세/월세 비교, 조건에 맞는 매물 리스트 정리, 단지 후보 찾기, and 자연어 기반 단지 비교/시세 요약. Use when the user wants Korean property listings, price ranges, Jeonse/monthly-rent comparisons, apartment/빌라 listing summaries, 지역명/단지명 기반 단지 후보 탐색, 여러 단지 비교 리포트, 자연어 채팅형 부동산 브리핑, 목표가/새 매물/가격하락 감시 초안, or 텔레그램 등 상위 레이어에 붙일 JSON/stdout 친화 결과 from Naver Real Estate. Prefer direct 단지 URL or complex ID first when rate-limited; otherwise use the natural-language wrapper and narrow to 1~3 candidate complexes before broad scans.
---

# Naver Real Estate Search

네이버 부동산 기반의 **대한민국 부동산 매물 검색 / 단지 후보 탐색 / 단지 비교 / 채팅형 브리핑 / 가격 감시** 스킬이다.

핵심 원칙:
- **단일 단지 우선**: URL/complex ID가 있으면 그걸 먼저 쓴다.
- **후보는 좁게**: 지역 전체를 넓게 긁기보다 후보 단지를 1~3개 먼저 좁힌다.
- **자연어 우선**: “잠실 리센츠 전세 30평대”, “은마와 래미안대치팰리스 비교”처럼 바로 넣는다.
- **한국어 브리핑 우선**: 채팅 표면에는 짧은 한국어 해석을 먼저 주고, 구조화 데이터가 필요할 때 JSON을 붙인다.
- **429 완화**: 짧은 백오프 후에도 막히면 direct URL/ID 기반 재조회 쪽으로 유도한다.

## Source dependency

이 스킬은 로컬 upstream clone을 래핑한다.

- `tmp/naverland-scrapper`

재사용하는 주요 로직:
- `src.core.parser.NaverURLParser`
- `src.core.services.response_capture.normalize_article_payload`
- `src.utils.helpers.PriceConverter`
- `src.utils.helpers.get_article_url`

## Scripts

### 1) 핵심 검색 엔진

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --self-test
```

역할:
- 자연어 파싱
- 후보 단지 탐색
- 단일 단지 조회
- 다중 단지 비교
- 동일 평형 요약
- JSON / 텍스트 출력

### 2) 채팅형 브리핑 래퍼

```bash
python skills/naver-real-estate-search/scripts/chat_real_estate.py --query "잠실 리센츠 전세 30평대"
```

역할:
- 단일 단지 결과를 더 자연스러운 한국어 브리핑으로 요약
- 여러 단지 비교 결과를 “어디가 더 낮은지 / 동일 평형이면 어디가 더 싼지 / 차이가 어느 정도인지” 중심으로 설명
- 대표 매물/링크를 채팅에 붙이기 쉽게 정리

### 3) 가격 감시 / 새 매물 감지

```bash
python skills/naver-real-estate-search/scripts/watch_real_estate.py add --name "리센츠 전세 30평대" --query "잠실 리센츠 전세 30평대" --target-max-price 950000000 --notify-on-new --notify-on-price-drop
python skills/naver-real-estate-search/scripts/watch_real_estate.py check --preview
python skills/naver-real-estate-search/scripts/watch_real_estate.py check --json
```

역할:
- 로컬 JSON 파일에 watch rule 저장
- 목표가 이하 / 새 매물 / 가격하락 감지
- `last_seen` / `events` / dedupe 기반의 실사용형 감시 초안 제공
- 텔레그램/브리핑 등 상위 레이어에 바로 전달하기 쉬운 stdout JSON 구조 제공

저장 파일:
- `skills/naver-real-estate-search/data/watch-rules.json`
- `skills/naver-real-estate-search/data/candidate-cache.json`
- `skills/naver-real-estate-search/references/candidate-seeds.json`

## Quick start

### 1) self-test
```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --self-test
```

### 2) 자연어 파싱만 확인
```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "잠실 리센츠랑 엘스 전세 비교 30평대" --parse-only
```

### 3) 후보 단지만 찾기
```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "서울 양천구 신월동 신월시영아파트 전세" --list-candidates --json
```

### 4) 채팅형 후보 리스트
```bash
python skills/naver-real-estate-search/scripts/chat_real_estate.py --query "대치 은마 전세" --list-candidates
```

### 4-1) candidate-cache seed / alias 학습
```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --seed-candidate-file
python skills/naver-real-estate-search/scripts/search_real_estate.py --seed-candidate --complex-id 1147 --candidate-name "리센츠" --candidate-address "서울특별시 송파구 잠실동" --candidate-aliases "잠실 리센츠,잠실리센츠"
python skills/naver-real-estate-search/scripts/search_real_estate.py --show-cache --query "리센츠"
```

반복 조회가 필요한 실존 단지나 alias가 자주 흔들리는 단지(예: `신월시영아파트`)는 먼저 cache에 학습시켜 둔다.

### 5) 단일 단지 조회
```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --complex-id 1147 --trade-types 전세 --limit 10
```

### 6) direct URL로 조회
```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --url "https://new.land.naver.com/complexes/1147" --trade-types 매매,전세 --json
```

### 7) 자연어 한 줄 브리핑
```bash
python skills/naver-real-estate-search/scripts/chat_real_estate.py --query "잠실 리센츠 전세 30평대" --limit 8
```

### 8) 여러 단지 비교 브리핑
```bash
python skills/naver-real-estate-search/scripts/chat_real_estate.py --query "잠실 리센츠와 잠실 엘스 전세 비교 30평대" --compare --candidate-limit 2
```

## Recommended workflow

1. 사용자가 **특정 단지 URL/ID**를 주면 그 값을 우선 사용한다.
2. URL/ID가 없으면 `chat_real_estate.py --query ...` 로 먼저 자연어 브리핑을 시도한다.
3. 질의가 넓거나 모호하면 `--list-candidates` 로 후보를 1~3개만 보여준다.
4. 후보가 좁혀지면 단일 단지 조회 또는 `--compare` 로 비교한다.
5. 구조화 데이터가 필요하면 같은 조건으로 `search_real_estate.py --json` 을 다시 호출한다.
6. 반복 확인이 필요하면 `watch_real_estate.py add/check` 흐름으로 가격 감시를 연결한다.

## Candidate-search guidance

현재 후보 탐색은 다음 순서로 동작한다.

1. direct complex ID / URL 우선 추출
2. 자연어에서 비교 대상 / 위치 힌트 / 거래유형 / 평형대 분리
3. 로컬 candidate cache(alias → complex_id) exact/contains 매칭
4. 캐시에 없으면 네이버 검색 결과 HTML에서 후보 complex ID 수집
5. 가능하면 단지 상세 API로 이름/주소/세대수 보강 후 캐시에 적재
6. 이름 정규화 / alias 일치 / 지역 힌트 / 질의 토큰 / 세대수 신뢰도 기준으로 점수화
7. 점수 상위 후보만 반환

`신월시영아파트 ↔ 신월시영` 같은 축약/별칭 차이를 줄이기 위해 공백 제거 + suffix 제거 + alias 확장을 같이 사용한다.

## Output guidance

### 단일 단지
- 단지명 / 위치
- 필터 요약(거래유형, 평형대)
- 건수 / 최저가 / 평균가 / 중앙값 / 최고가
- 대표 동일 평형 요약
- 대표 매물 2~3개
- 사람이 읽기 쉬운 짧은 해석

### 여러 단지 비교
- 단지별 핵심 수치
- 전체 평균 기준 어느 단지가 더 낮은지
- 가능한 경우 동일 평형 기준 어느 단지가 더 낮은지
- 대표 매물 또는 링크

### 가격 감시
- rule 이름 / id
- 목표가 이하 매물 수
- 신규 매물 / 가격하락 감지
- stdout JSON의 `alerts`, `snapshot`, `events`, `message_preview`, `summary` 계층 활용
- 텔레그램/브리핑 레이어에는 `watch_real_estate.py check --preview` 결과를 바로 붙이고, 구조화 후처리가 필요하면 `--json`을 사용

## References

세부 설계/429 운영 지침/감시 schema/seed 예시는 다음 파일을 참고한다.

- `references/design.md`
- `references/candidate-seeds.json`
