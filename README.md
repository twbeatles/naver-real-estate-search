# naver-real-estate-search

네이버 부동산 기반으로 대한민국 아파트/빌라/오피스텔 매물 조회, 단지 후보 탐색, 비교 브리핑, 가격 감시를 수행하는 OpenClaw 스킬입니다.

## 주요 개선점
- alias/후보 캐시 구조 강화 (`candidate-cache.json` v2 스타일)
- 지역명/단지명 파서 보강, cold-start 후보 탐색 품질 개선
- `신월시영아파트` 같은 축약/별칭 케이스 보강
- 429 감지 시 direct URL/complex ID 우선 흐름을 유지하는 fallback 메타 추가
- 동일 평형 기준 비교 요약 추가
- 한국어 비교 브리핑과 대표 매물 요약 개선
- watch schema 확장: `last_seen`, `events`, dedupe, 새 매물/가격하락 감지
- 상위 레이어(텔레그램/브리핑) 연동용 stdout JSON 구조 개선

## 스크립트

### 1) 후보 탐색 / 단일 조회 / 비교
```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "잠실 리센츠 전세 30평대"
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "잠실 리센츠와 엘스 전세 비교 30평대" --compare --json
python skills/naver-real-estate-search/scripts/search_real_estate.py --query "서울 양천구 신월동 신월시영아파트 전세" --list-candidates --json
```

### 2) 채팅형 브리핑
```bash
python skills/naver-real-estate-search/scripts/chat_real_estate.py --query "잠실 리센츠 전세 30평대"
python skills/naver-real-estate-search/scripts/chat_real_estate.py --query "잠실 리센츠와 엘스 전세 비교 30평대" --compare
```

### 3) 가격 감시 / 새 매물 감지
```bash
python skills/naver-real-estate-search/scripts/watch_real_estate.py add --name "리센츠 전세 30평대" --query "잠실 리센츠 전세 30평대" --target-max-price 950000000 --notify-on-new --notify-on-price-drop
python skills/naver-real-estate-search/scripts/watch_real_estate.py check --json
```

## 저장 파일
- `data/candidate-cache.json`: 후보 단지 alias/주소/ID 캐시
- `data/watch-rules.json`: 감시 규칙 + 최근 관측 상태 + 이벤트 히스토리

## 배포 체크리스트
1. self-test 실행
2. 대표 자연어 질의/후보 탐색/감시 check 실제 실행
3. skill 패키징
4. GitHub tag/release 및 ClawHub publish
