# naver-real-estate-search 설계 메모

## 목표
- 대한민국 / 네이버 부동산 맥락에 맞는 OpenClaw 스킬 제공
- 자연어 요청을 빠르게 최소 실행 가능한 검색 파라미터로 바꾸기
- `twbeatles/naverland-scrapper`의 내부 로직을 가능한 범위에서 재사용

## 재사용한 upstream 로직
- `src.core.parser.NaverURLParser`
  - 네이버 부동산 URL/텍스트에서 `complex_id` 추출
  - 단지명 조회 로직 재사용
- `src.core.services.response_capture.normalize_article_payload`
  - 네이버 API article payload를 한국어 필드 구조로 정규화
- `src.utils.helpers.PriceConverter`
  - 가격 문자열 ↔ 정수 비교/정렬
- `src.utils.helpers.get_article_url`
  - 매물 URL 재구성

## 최소 기능 범위
1. 단지 URL 또는 complex ID 입력
2. 지역/단지 키워드 입력 시 웹 검색 결과에서 complex ID 후보 추출 시도
3. 매매/전세/월세 중 1개 이상 조회
4. 상위 N개 매물 요약 또는 JSON 출력
5. 평수 범위 간단 필터

## 제약
- upstream repo는 GUI 앱 중심이라 CLI 검색 엔트리포인트가 없음
- 네이버 부동산 API가 429를 반환할 수 있어 live 검색이 불안정함
- MVP는 429 발생 시 명시적으로 안내하고, direct URL/ID 입력을 우선 권장함

## 후속 개선 아이디어
- Playwright 기반 브라우저 세션을 활용한 429 우회/쿠키 재사용
- 지역명 → 단지 후보 검색 정확도 향상
- 같은 지역 내 복수 단지 비교 모드
- 가격/면적/층/방향/자산유형 복합 필터 추가
- 시세 요약(최저/중앙/최고) 및 비교 리포트 포맷 강화
