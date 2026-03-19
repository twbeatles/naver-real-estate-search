---
name: naver-real-estate-search
description: Search 네이버 부동산 listings and 단지 candidates for 대한민국 real-estate requests such as 강남 아파트 전세 시세 찾기, 특정 지역 매매/전세/월세 비교, 조건에 맞는 매물 리스트 정리, 단지 후보 찾기, and 자연어 기반 단지 비교/시세 요약. Use when the user wants Korean property listings, price ranges, Jeonse/monthly-rent comparisons, apartment/빌라 listing summaries, 지역명/단지명 기반 단지 후보 탐색, 여러 단지 비교 리포트, 자연어 채팅형 부동산 브리핑, or 간단한 목표가 기반 가격 감시 초안 from Naver Real Estate. Prefer direct 단지 URL or complex ID first when rate-limited; otherwise use the natural-language wrapper and narrow to 1~3 candidate complexes before broad scans.
---

# Naver Real Estate Search

네이버 부동산 기반의 **대한민국 부동산 매물 검색 / 단지 후보 탐색 / 단지 비교 / 채팅형 브리핑 / 간단한 가격 감시 초안** 스킬이다.

핵심 원칙:
- **단일 단지 우선**: URL/complex ID가 있으면 그걸 먼저 사용한다.
- **후보는 좁게**: 지역명만 넓게 긁지 말고, 단지 후보를 1~3개로 먼저 좁힌다.
- **자연어 우선**: 사용자가 “잠실 리센츠 전세 30평대”, “은마랑 래미안대치팰리스 비교”처럼 말하면 그대로 `--query` 로 처리한다.
- **채팅 응답은 사람말처럼**: JSON보다 먼저 짧은 한국어 브리핑을 만들고, 필요할 때만 구조화 데이터를 붙인다.
- **429 완화**: 자동 짧은 백오프를 하되, 계속 막히면 더 넓은 스캔 대신 **직접 단지 URL/ID 요청**으로 전환한다.

## Source dependency

이 스킬은 로컬 upstream clone을 래핑한다.

- `tmp/naverland-scrapper`

재사용하는 주요 로직:
- `src.core.parser.NaverURLParser`
- `src.core.services.response_capture.normalize_article_payload`
- `src.utils.helpers.PriceConverter`
- `src.utils.helpers.get_article_url`

upstream clone 또는 Python 의존성이 없으면 검색이 실패할 수 있다.

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
- JSON / 텍스트 출력

### 2) 채팅형 브리핑 래퍼

```bash
python skills/naver-real-estate-search/scripts/chat_real_estate.py --query "잠실 리센츠 전세 30평대"
```

역할:
- 단일 단지 결과를 더 자연스러운 한국어 브리핑으로 요약
- 여러 단지 비교 결과를 “어디가 더 낮은지 / 차이가 어느 정도인지” 중심으로 설명
- 채팅 표면에 바로 붙이기 쉬운 문장형 응답 생성

### 3) 가격 감시 초안

```bash
python skills/naver-real-estate-search/scripts/watch_real_estate.py add --name "리센츠 전세 30평대" --query "잠실 리센츠 전세 30평대" --target-max-price 950000000
python skills/naver-real-estate-search/scripts/watch_real_estate.py check
```

역할:
- 로컬 JSON 파일에 watch rule 저장
- 현재 매물 중 목표가 이하 항목 점검
- 알림 연동 전 단계의 저장/점검 베이스 제공

저장 파일:
- `skills/naver-real-estate-search/data/watch-rules.json`

## Quick start

### 1) self-test

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --self-test
```

### 2) 자연어 질의 파싱만 확인

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "잠실 리센츠랑 엘스 전세 비교 30평대" --parse-only
```

### 3) 후보 단지만 찾기

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "대치 은마 전세" --list-candidates --json
```

### 4) 채팅형 후보 리스트

```bash
python skills/naver-real-estate-search/scripts/chat_real_estate.py --query "대치 은마 전세" --list-candidates
```

### 5) 단일 단지 전세 조회

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --complex-id 1147 --trade-types 전세 --limit 10
```

### 6) 네이버 부동산 URL로 조회

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

## Parameters

공통적으로 자주 쓰는 옵션:
- `--query`: 자연어 또는 지역/단지 키워드
- `--complex-id`: 네이버 부동산 단지 ID
- `--url`: 네이버 부동산 단지/매물 URL
- `--trade-types`: 쉼표 구분 거래 유형
- `--pages`: 네이버 API 페이지 수
- `--limit`: 단지별 출력 최대 매물 개수
- `--candidate-limit`: 후보 단지 최대 개수
- `--min-pyeong`, `--max-pyeong`: 평수 범위 강제 지정
- `--json`: 구조화 출력

`search_real_estate.py` 전용:
- `--list-candidates`
- `--compare`
- `--parse-only`
- `--self-test`

`chat_real_estate.py` 전용:
- `--list-candidates`
- `--compare`

`watch_real_estate.py` 전용:
- `add`, `list`, `check`
- `--target-max-price`: 정수 가격 기준값

## Recommended workflow

1. 사용자가 **특정 단지 URL/ID**를 주면 그 값을 우선 사용한다.
2. URL/ID가 없으면 `chat_real_estate.py --query ...` 로 먼저 자연어 브리핑을 시도한다.
3. 질의가 넓거나 모호하면 `--list-candidates` 로 후보를 1~3개만 보여준다.
4. 후보가 좁혀지면 단일 단지 조회 또는 `--compare` 로 비교한다.
5. 구조화 데이터가 필요하면 같은 조건으로 `search_real_estate.py --json` 을 다시 호출한다.
6. 반복 확인이 필요한 경우 `watch_real_estate.py add/check` 흐름으로 가격 감시 초안을 연결한다.

## Candidate-search guidance

현재 후보 탐색은 다음 순서로 동작한다.

1. 텍스트/URL 안의 direct complex ID 우선 추출
2. 자연어에서 비교 대상 / 위치 힌트 / 거래유형 / 평형대 분리
3. 네이버 검색 결과에서 후보 ID 수집
4. 단지 상세 API로 이름/주소/세대수 보강
5. **이름 일치 + 주소 내 지역 힌트 + 전체 질의 토큰 매칭** 기준으로 점수화
6. 점수 상위 후보만 반환

즉, 예전처럼 “ID만 긁어서 순서대로” 내는 게 아니라, **사용자 질의와 더 잘 맞는 단지를 위로 올리는 랭킹**이 들어간다.

## Natural-language handling

현재 래퍼는 다음을 자동 추론한다.
- 거래유형: `매매`, `전세`, `월세`
- 평수: `30평대`, `25평`, `25평~34평`
- 비교 의도: `비교`, `대비`, `A와 B`, `A랑 B`
- 위치 힌트: `잠실`, `대치동`, `강남구` 같은 한국 지역 토큰
- 후보 키워드 분리: `리센츠와 엘스`, `은마, 래미안대치팰리스`

모호한 경우에는:
- 먼저 후보 목록을 보여주고
- 사용자가 하나를 고르게 한 뒤
- 선택된 단지 기준으로 재조회한다.

## Output guidance

채팅 응답에서는 보통 아래 순서로 정리한다.

### 단일 단지
- 단지명 / 위치
- 필터 요약(거래유형, 평형대)
- 건수 / 최저가 / 평균가 / 최고가
- 대표 매물 2~3개
- 사람이 읽기 쉬운 짧은 해석

### 여러 단지 비교
- 단지별 핵심 수치
- 어느 단지가 상대적으로 낮은지
- 평균 기준 격차가 어느 정도인지
- 필요하면 대표 매물 링크

### 가격 감시 초안
- rule 이름
- 목표가 이하 매물 수
- 걸린 대표 매물 링크
- 추후 텔레그램/다른 채널 알림 연결 가능성을 염두에 둔 구조 유지

## Limitations

- upstream repo는 GUI 앱 중심이라 이 스킬은 별도 CLI 래퍼를 제공한다.
- 네이버 부동산 API는 rate-limit(429)이 걸릴 수 있다.
- 후보 탐색은 검색 결과 HTML을 기반으로 하므로 네이버 마크업 변경에 민감할 수 있다.
- 가격 감시는 아직 **로컬 rule 저장 + 점검** 수준이며, 자동 푸시 알림까지는 연결되지 않았다.
- 광역 지역 전체 시세 스캔보다 **단일 단지 / 소수 단지 비교**에 더 안정적이다.

## References

세부 설계/429 운영 지침/확장 아이디어는 다음 파일을 참고한다.

- `references/design.md`
