---
name: naver-real-estate-search
description: Search 네이버 부동산 listings and 단지 candidates for 대한민국 real-estate requests such as 강남 아파트 전세 시세 찾기, 특정 지역 매매/전세/월세 비교, 조건에 맞는 매물 리스트 정리, 단지 후보 찾기, and 자연어 기반 단지 비교/시세 요약. Use when the user wants Korean property listings, price ranges, Jeonse/monthly-rent comparisons, apartment/빌라 listing summaries, 지역명/단지명 기반 단지 후보 탐색, or 여러 단지 비교 리포트 from Naver Real Estate. Prefer direct 단지 URL or complex ID first when rate-limited; otherwise use the natural-language wrapper and narrow to 1~3 candidate complexes before broad scans.
---

# Naver Real Estate Search

네이버 부동산 기반의 **대한민국 부동산 매물 검색/단지 후보 탐색/단지 비교용 스킬**이다.

핵심 원칙:
- **단일 단지 우선**: URL/complex ID가 있으면 그걸 먼저 사용한다.
- **후보는 좁게**: 지역명만 넓게 긁지 말고, 단지 후보를 1~3개로 먼저 좁힌다.
- **429 완화**: 자동 짧은 백오프를 하되, 계속 막히면 더 넓은 스캔 대신 **직접 단지 URL/ID 요청**으로 전환한다.
- **자연어 우선**: 사용자가 “잠실 리센츠 전세 30평대”, “은마랑 래미안대치팰리스 비교”처럼 말하면 그대로 `--query` 로 처리한다.

## Source dependency

이 스킬은 로컬 upstream clone을 래핑한다.

- `tmp/naverland-scrapper`

재사용하는 주요 로직:
- `src.core.parser.NaverURLParser`
- `src.core.services.response_capture.normalize_article_payload`
- `src.utils.helpers.PriceConverter`
- `src.utils.helpers.get_article_url`

upstream clone 또는 Python 의존성이 없으면 검색이 실패할 수 있다.

## Quick start

### 1) self-test

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --self-test
```

### 2) 자연어 질의 파싱만 확인

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "잠실 리센츠랑 엘스 전세 비교 30평대" --parse-only
```

### 3) 단지 후보만 찾기

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "대치 은마 전세" --list-candidates --json
```

### 4) 단일 단지 전세 조회

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --complex-id 1147 --trade-types 전세 --limit 10
```

### 5) 네이버 부동산 URL로 조회

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --url "https://new.land.naver.com/complexes/1147" --trade-types 매매,전세 --json
```

### 6) 자연어 한 줄로 조회

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "잠실 리센츠 전세 30평대" --limit 10
```

### 7) 여러 단지 비교

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "잠실 리센츠와 잠실 엘스 전세 비교 30평대" --compare --candidate-limit 2 --json
```

## Parameters

- `--query`: 자연어 또는 지역/단지 키워드. 예: `강남 아파트 전세`, `대치 은마와 래미안대치팰리스 비교`, `잠실 리센츠 전세 30평대`
- `--complex-id`: 네이버 부동산 단지 ID
- `--url`: 네이버 부동산 단지/매물 URL
- `--trade-types`: 쉼표 구분 거래 유형. 비우면 질의에서 추론하고, 없으면 기본값 `전세`
- `--pages`: 네이버 API 페이지 수. 기본값 `1`
- `--limit`: 단지별 출력 최대 매물 개수
- `--candidate-limit`: 후보 단지 최대 개수. 기본값 `3`
- `--min-pyeong`, `--max-pyeong`: 평수 범위 강제 지정
- `--list-candidates`: 매물 조회 대신 단지 후보만 출력
- `--compare`: 후보 상위 단지를 비교 모드로 조회
- `--parse-only`: 자연어 파싱 결과만 출력
- `--json`: JSON 출력
- `--self-test`: 정규화/자연어 파싱 자체 테스트

## Recommended workflow

1. 사용자가 **특정 단지 URL/ID**를 주면 그 값을 우선 사용한다.
2. URL/ID가 없으면 `--query` 로 자연어를 바로 넣는다.
3. 질의가 넓으면 먼저 `--list-candidates` 로 후보를 1~3개만 뽑는다.
4. 그다음 단일 단지 조회 또는 `--compare` 로 비교한다.
5. 429가 발생하면:
   - 자동 짧은 백오프 후 재시도는 이미 들어가 있다.
   - 그래도 실패하면 **광역 검색을 멈추고** 단지 URL/ID 직접 입력으로 전환한다.
   - 가능하면 “강남 전세” 대신 “대치 은마 전세 30평대”처럼 더 구체화한다.

## Natural-language handling

현재 래퍼는 다음을 자동 추론한다.
- 거래유형: `매매`, `전세`, `월세`
- 평수: `30평대`, `25평`, `25평~34평`
- 비교 의도: `비교`, `대비`, `A와 B`, `A랑 B`
- 후보 키워드 분리: `리센츠와 엘스`, `은마, 래미안대치팰리스`

완벽한 NLU는 아니므로 모호한 경우에는:
- 후보 목록을 먼저 보여주고
- 사용자가 고를 수 있게 한 뒤
- 선택된 단지 기준으로 재조회한다.

## Output guidance

채팅 응답에서는 보통 아래 순서로 요약한다.

### 단일 단지
- 검색 대상: 단지명 / ID
- 거래유형별 건수
- 최저가 / 평균가 / 최고가
- 대표 매물 3~5개
- 특이사항: 월세면 `보증금/월세`, 전세면 전세금, 매매면 매매가 강조

### 여러 단지 비교
- 비교 대상 단지 목록
- 단지별 거래유형 건수
- 단지별 최저 / 평균 / 최고 가격
- 같은 평형대 기준으로 눈에 띄는 차이
- 필요하면 대표 매물 링크 1~3개

구조화 데이터가 필요하면 `--json`을 사용한다.

## Limitations

- upstream repo는 GUI 앱 중심이라 이 스킬은 별도 CLI 래퍼를 제공한다.
- 네이버 부동산 API는 rate-limit(429)이 걸릴 수 있다.
- 후보 탐색은 현재 검색 결과 HTML 기반이라, **정확도보다 실용적 좁히기**에 가깝다.
- 광역 지역 전체 시세 스캔보다 **단일 단지/소수 단지 비교**에 더 안정적이다.

## References

세부 설계/429 운영 지침/확장 아이디어는 다음 파일을 참고한다.

- `references/design.md`
