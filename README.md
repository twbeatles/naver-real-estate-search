# naver-real-estate-search

대한민국 **네이버 부동산 매물 검색/단지 비교용** OpenClaw 스킬입니다.

`twbeatles/naverland-scrapper`의 핵심 로직을 재사용해, 네이버 부동산 기반으로 **단일 단지 조회**, **여러 단지 비교**, **자연어 질의 파싱**, **평수/거래유형 추론**을 수행하는 최소 기능 버전입니다.

> 핵심 원칙: 광역 검색을 무리하게 돌리기보다 **단일 단지 우선**, **후보 1~3개 좁히기**, **그 다음 비교** 흐름으로 쓰는 것이 가장 안정적입니다.

---

## 지원 범위

현재 버전에서 지원하는 기능:

- 네이버 부동산 **단일 단지 매물 조회**
- **단지 URL / complex ID 직접 조회**
- 자연어 질의 파싱
  - `매매 / 전세 / 월세` 추론
  - `30평대`, `25평`, `25평~34평` 추론
  - `비교`, `A와 B`, `A랑 B`, `vs` 감지
- **단지 후보 탐색**
- **여러 단지 비교 / 시세 요약**
- JSON 출력
- 텍스트 요약 출력
- `--parse-only` 로 자연어 파싱 검증 가능

현재 버전에서 한계가 있는 부분:

- 네이버 API **429(요청 제한)** 영향을 받을 수 있음
- 광역 지역 전체 검색은 정확도/안정성이 낮음
- 후보 탐색은 현재 검색 HTML 기반이라 완벽하지 않음

---

## 저장소 구조

```text
naver-real-estate-search/
├── README.md
├── SKILL.md
├── references/
│   └── design.md
└── scripts/
    └── search_real_estate.py
```

---

## 빠른 시작

### 1) self-test

```bash
python scripts/search_real_estate.py --self-test
```

### 2) 자연어 파싱만 확인

```bash
python scripts/search_real_estate.py --query "잠실 리센츠와 엘스 전세 비교 30평대" --parse-only
```

### 3) 단지 후보만 찾기

```bash
python scripts/search_real_estate.py --query "대치 은마 전세" --list-candidates --json
```

### 4) 단일 단지 전세 조회

```bash
python scripts/search_real_estate.py --complex-id 1147 --trade-types 전세 --limit 10
```

### 5) 단지 URL로 조회

```bash
python scripts/search_real_estate.py --url "https://new.land.naver.com/complexes/1147" --trade-types 매매,전세 --json
```

### 6) 자연어 한 줄로 조회

```bash
python scripts/search_real_estate.py --query "잠실 리센츠 전세 30평대" --limit 10
```

### 7) 여러 단지 비교

```bash
python scripts/search_real_estate.py --query "잠실 리센츠와 잠실 엘스 전세 비교 30평대" --compare --candidate-limit 2 --json
```

---

## 자연어 입력 예시

이 스킬은 아래 같은 질의를 해석하도록 설계했습니다.

- `잠실 리센츠 전세 30평대`
- `은마와 래미안대치팰리스 비교`
- `강남 아파트 전세 시세 찾아줘`
- `대치동 전세 25평~34평`
- `잠실 리센츠랑 엘스 전세 비교`

현재 자동 추론하는 것:
- 거래유형: `매매`, `전세`, `월세`
- 평수: `30평대`, `25평`, `25평~34평`
- 비교 의도: `비교`, `대비`, `와`, `과`, `랑`, `vs`
- 후보 키워드 분리

---

## 추천 사용 흐름

### 가장 안정적인 방법
1. **단지 URL 또는 complex ID가 있으면 먼저 사용**
2. 없으면 `--query`로 자연어 입력
3. 검색 범위가 넓으면 `--list-candidates`로 후보 1~3개만 확인
4. 그 다음 단일 단지 조회 또는 `--compare`

예를 들어:
- `강남 전세`처럼 너무 넓게 넣는 것보다
- `대치 은마 전세 30평대`처럼 좁혀서 쓰는 게 좋음

---

## 429 대응 전략

네이버 부동산 API는 실제 환경에서 **429(Too Many Requests)** 를 반환할 수 있습니다.

현재 버전에서 반영된 대응:
- 짧은 **백오프 재시도** (`1.5초`, `3초`)
- 그래도 실패하면 더 좁은 검색을 유도하는 메시지 출력

실전 팁:
- 광역 검색보다 **단일 단지 조회**가 훨씬 안정적
- 후보 검색도 `1~3개` 정도로 좁혀서 진행하는 편이 좋음
- 가능하면 **단지 URL/ID 직접 입력**이 제일 안정적

---

## 출력 예시

### parse-only 예시

```bash
python scripts/search_real_estate.py --query "잠실 리센츠와 엘스 전세 비교 30평대" --parse-only
```

의도:
- 거래유형 추론: `전세`
- 평수 추론: `30평대`
- 비교 모드: `true`
- 후보 키워드: `리센츠`, `엘스`

### compare 예시

```bash
python scripts/search_real_estate.py --query "은마와 래미안대치팰리스 비교" --compare --candidate-limit 2 --json
```

출력 개요:
- 단지별 매물 수
- 거래유형별 건수
- 최저 / 평균 / 최고가
- 대표 매물 링크

---

## 현재 한계

- 후보 탐색은 아직 검색 HTML 기반이라 정확도가 완벽하지 않음
- 지역명만 넣은 광역 검색은 단지 후보 품질이 떨어질 수 있음
- 동일 평형 기준의 정교한 비교는 아직 MVP 수준
- live 환경에선 429가 실사용성의 가장 큰 제약

---

## 다음 개선 후보

다음 단계로 붙이면 좋은 것:
- Playwright 세션/쿠키 기반 429 완화
- 지역명 → 단지 후보 탐색 정확도 향상
- 동일 평형 중심 비교 고도화
- 자연어 채팅 래퍼 추가
- 가격 알림 기능과 연결

---

## 출처

이 저장소는 `twbeatles/naverland-scrapper`를 기반으로 OpenClaw 스킬 형태로 재구성한 파생 작업입니다.
