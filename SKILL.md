---
name: naver-real-estate-search
description: Search 네이버 부동산 listings for 대한민국 real-estate requests such as 강남 아파트 전세 시세 찾기, 특정 지역 매매/전세/월세 비교, and 조건에 맞는 매물 리스트 정리. Use when the user wants Korean property listings, price ranges, Jeonse/monthly-rent comparisons, or apartment/빌라 listing summaries from Naver Real Estate. Prefer this skill for 네이버 부동산 기반 지역/단지/매물 탐색; ask for a direct 단지 URL or complex ID when live API search is rate-limited.
---

# Naver Real Estate Search

네이버 부동산 기반의 **대한민국 부동산 매물 검색용 스킬**이다.

현재 MVP 범위:
- 단지 URL 또는 complex ID 기반 매물 조회
- 지역/단지 키워드 기반 complex ID 후보 추출 시도
- 매매/전세/월세 조회
- 간단한 평수 필터
- 한국어 요약 또는 JSON 출력

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

### 2) 단지 ID로 전세 조회

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --complex-id 1147 --trade-types 전세 --limit 10
```

### 3) 네이버 부동산 URL로 조회

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --url "https://new.land.naver.com/complexes/1147" --trade-types 매매,전세 --json
```

### 4) 지역/단지 키워드로 후보 추출 + 조회 시도

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "강남 아파트 전세" --trade-types 전세 --limit 10
```

### 5) 평수 조건 포함

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "대치동 아파트" --trade-types 매매,전세 --min-pyeong 25 --max-pyeong 40 --limit 15
```

## Parameters

- `--query`: 지역/단지 키워드. 예: `강남 아파트 전세`, `대치동 아파트`
- `--complex-id`: 네이버 부동산 단지 ID
- `--url`: 네이버 부동산 단지/매물 URL
- `--trade-types`: 쉼표 구분 거래 유형. 기본값 `전세`
- `--pages`: 네이버 API 페이지 수. 기본값 `1`
- `--limit`: 최종 출력 최대 개수
- `--min-pyeong`, `--max-pyeong`: 간단한 평수 범위 필터
- `--json`: JSON 출력
- `--self-test`: upstream 정규화 로직 재사용 여부를 빠르게 검증

## Recommended workflow

1. 사용자가 **특정 단지 URL/ID**를 주면 그 값을 우선 사용한다.
2. URL/ID가 없으면 `--query`로 시도한다.
3. 429가 발생하면:
   - 잠시 후 재시도한다.
   - 사용자에게 단지 URL/ID를 직접 달라고 요청한다.
   - 넓은 지역 검색 대신 더 구체적인 단지명을 요청한다.
4. 결과를 전달할 때는 다음처럼 정리한다:
   - 거래유형별 건수
   - 가격 범위
   - 대표 매물 몇 개
   - 필요하면 평수/층/방향 기준 추가 정리

## Output guidance

채팅 응답에서는 보통 아래 순서로 요약한다.

- 검색 대상: 지역/단지명
- 거래유형별 건수
- 최저가/최고가
- 대표 매물 3~5개
- 특이사항: 월세면 `보증금/월세`, 전세면 전세금, 매매면 매매가 강조

구조화 데이터가 필요하면 `--json`을 사용한다.

## Limitations

- upstream repo는 GUI 앱 중심이라 이 스킬은 별도 CLI 래퍼를 제공한다.
- 네이버 부동산 API는 rate-limit(429)이 걸릴 수 있다.
- MVP는 복수 단지 동시 비교보다는 **단일 단지 중심 검색**에 더 안정적이다.
- 광역 지역 전체 시세 스캔은 후속 개선 대상이다.

## References

설계 배경과 재사용 컴포넌트는 다음 파일을 참고한다.

- `references/design.md`
