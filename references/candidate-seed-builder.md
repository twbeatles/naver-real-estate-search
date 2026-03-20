# candidate seed 자동 생성 메모

## 목적
- 서울 주요 단지 seed 리스트를 입력받아 `candidate-seeds.generated.json` 초안을 만든다.
- 기존 `candidate-seeds.json`, `candidate-cache.json`, `search_real_estate.py`와 연결 가능한 구조를 유지한다.
- 운영용 승격 기준은 `verification_status in {verified, weak-verified}` 로 둔다.

## 입력/출력

### 입력
- `references/seoul-major-complexes.seed-input.json`
- shape:

```json
{
  "seeds": [
    {
      "name": "리센츠",
      "city": "서울특별시",
      "district": "송파구",
      "neighborhood": "잠실동",
      "aliases": ["잠실 리센츠", "잠실리센츠"]
    }
  ]
}
```

### 출력
- `references/candidate-seeds.generated.json`
- 핵심 필드:
  - `entries[]`: 검증 통과한 운영 투입 후보
  - `results[]`: 전체 생성 결과 + evidence
  - `unresolved[]`: 후속 수동 검증 대상

## 생성 순서
1. 입력 seed의 이름/지역을 바탕으로 alias를 자동 확장한다.
2. 기존 `references/candidate-seeds.json`의 verified baseline과 이름/alias exact 매칭을 먼저 본다.
3. `candidate-cache.json` exact/contains 매칭으로 warm-cache 힌트를 찾는다.
4. 네이버 검색 HTML에서 complex link/ID를 추출한다.
5. 가능하면 단지 상세 API로 이름/주소/세대수를 조회해 검증한다.
6. `confidence`, `verification_status`, `candidate_pool`, `evidence`, `blocked_reasons`를 남긴다.

## 운영 권장
- `entries[]`만 `search_real_estate.py --seed-candidate-file <file>`로 넣는다.
- `results[]`에 complex_id가 있어도 `verification_status`가 `unverified`면 자동 투입하지 않는다.
- 403/429가 반복되면 broad query 대신 direct complex URL/ID로 수동 보강한다.

## 실제 테스트 요약 (2026-03-20)

실행:

```bash
python skills/naver-real-estate-search/scripts/search_real_estate.py --self-test
python skills/naver-real-estate-search/scripts/build_candidate_seeds.py --print-summary
```

관찰:
- `search_real_estate.py --self-test` 성공
- 생성기 1건 단일 테스트에서 `리센츠 -> 1147` verified 확인
- 전체 서울 샘플 실행에서는 baseline/cache 덕분에 `리센츠`만 안정적으로 verified
- `엘스`, `트리지움`은 rate-limit(429) 환경에서 잘못된 cache candidate가 끼어들 수 있어 `unverified`로만 남김
- `은마`, `래미안대치팰리스`, `아크로리버파크`, `래미안원베일리`, `목동신시가지7단지`, `신월시영아파트`는 자동 생성만으로는 미해결 또는 blocked 상태
- 네이버 검색 HTML은 일부 질의에서 링크 추출이 0건으로 끝났고, 상세 API는 반복 조회 시 429가 발생함

## 한계
- 검색 HTML 구조 변화에 취약하다.
- 네이버 상세 API 429 발생 시 검증 성공률이 크게 떨어진다.
- warm-cache가 부족하면 broad query만으로는 서울 주요 단지 전체를 안정적으로 맞추기 어렵다.
- 따라서 자동 생성은 초안/보조 도구로 보고, 운영 seed는 검증 승격 단계를 두는 것이 안전하다.
