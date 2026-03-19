from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[3]
UPSTREAM = WORKSPACE / "tmp" / "naverland-scrapper"
SRC_ROOT = UPSTREAM / "src"
if str(UPSTREAM) not in sys.path:
    sys.path.insert(0, str(UPSTREAM))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from src.core.parser import NaverURLParser
from src.core.services.response_capture import normalize_article_payload
from src.utils.helpers import PriceConverter, get_article_url

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
SEARCH_URL = "https://search.naver.com/search.naver?where=nexearch&sm=top_hty&fbm=0&ie=utf8&query={query}"
COMPLEX_DETAIL_URL = "https://new.land.naver.com/api/complexes/{complex_id}?sameAddressGroup=false"
COMPLEX_ARTICLE_URL = (
    "https://new.land.naver.com/api/articles/complex/{complex_id}?"
    "realEstateType=APT%3AVL&tradeType={trade_codes}&tag=%3A%3A%3A%3A%3A%3A%3A%3A"
    "&rentPriceMin=0&rentPriceMax=900000000&priceMin=0&priceMax=900000000"
    "&areaMin=0&areaMax=900000000&oldBuildYears=&recentlyBuildYears=&minHouseHoldCount="
    "&maxHouseHoldCount=&showArticle=false&sameAddressGroup=false&minMaintenanceCost=&maxMaintenanceCost="
    "&priceType=RETAIL&directions=&page={page}&complexNo={complex_id}&buildingNos=&areaNos=&type=list&order=rank"
)
TRADE_CODE_MAP = {"매매": "A1", "전세": "B1", "월세": "B2"}
DEFAULT_QUERY_SUFFIX = " 네이버 부동산 아파트"
DEFAULT_BACKOFFS = [1.5, 3.0]
STOPWORDS = [
    "네이버 부동산", "부동산", "시세", "매물", "가격", "가격대", "얼마", "비교", "정리", "요약", "알려줘", "찾아줘",
    "보여줘", "조회", "검색", "추천", "아파트", "빌라", "오피스텔", "실거래가", "단지", "찾기", "브리핑",
    "해줘", "해주세요", "알림", "감시", "체크", "체크해줘", "요청", "보고", "리포트", "채팅", "래퍼",
]
TRADE_STOPWORDS = ["매매", "전세", "월세"]
COMPARE_TOKENS = ["비교", "대비", "vs", "VS"]
LOCATION_HINT_RE = re.compile(r"([가-힣]{2,}(?:시|도|군|구|동|읍|면|리|가))")
SIMPLE_KOREAN_TOKEN_RE = re.compile(r"[가-힣]{2,}")
WATCH_STATE_FILE = WORKSPACE / "skills" / "naver-real-estate-search" / "data" / "watch-rules.json"


class SearchError(RuntimeError):
    pass


@dataclass
class ParsedQuery:
    raw_query: str
    cleaned_query: str
    trade_types: list[str]
    min_pyeong: float | None
    max_pyeong: float | None
    compare_mode: bool
    candidate_keywords: list[str]
    location_hints: list[str]


def _request_json(url: str, *, referer: str = "https://new.land.naver.com/", backoffs: list[float] | None = None) -> Any:
    backoffs = DEFAULT_BACKOFFS if backoffs is None else backoffs
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Referer", referer)
    req.add_header("Accept", "application/json, text/plain, */*")
    attempts = len(backoffs) + 1
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            if exc.code == 429 and attempt < len(backoffs):
                time.sleep(backoffs[attempt])
                continue
            if exc.code == 429:
                raise SearchError(
                    "네이버 부동산 API가 429(요청 제한)를 반환했습니다. 단일 단지 URL/ID를 우선 사용하고, 후보 검색은 1~3개만 좁혀서 다시 시도해 주세요."
                )
            raise SearchError(f"네이버 부동산 API 호출 실패: HTTP {exc.code} {body[:200]}")
        except Exception as exc:
            raise SearchError(f"네이버 부동산 API 호출 실패: {exc}") from exc
    raise SearchError("네이버 부동산 API 호출 실패")


def _request_text(url: str) -> str:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read().decode("utf-8", errors="ignore")


def normalize_keyword(text: str) -> str:
    value = str(text or "").strip()
    for token in STOPWORDS + TRADE_STOPWORDS:
        value = value.replace(token, " ")
    value = re.sub(r"\b\d+\s*평(?:대|형)?\b", " ", value)
    value = re.sub(r"\b\d+\s*(?:평|형)\b", " ", value)
    value = re.sub(r"\b\d+\s*[~-]\s*\d+\s*평\b", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" ,/")
    return value


def parse_trade_types(query: str) -> list[str]:
    hits = []
    for trade in ["매매", "전세", "월세"]:
        if trade in query:
            hits.append(trade)
    return hits or ["전세"]


def parse_pyeong_range(query: str) -> tuple[float | None, float | None]:
    m = re.search(r"(\d{1,2})\s*평대", query)
    if m:
        base = float(m.group(1))
        return max(0.0, base - 3), base + 3
    m = re.search(r"(\d{1,2})\s*평\s*[~-]\s*(\d{1,2})\s*평", query)
    if m:
        return float(m.group(1)), float(m.group(2))
    single = re.search(r"(\d{1,2})\s*평", query)
    if single:
        base = float(single.group(1))
        return max(0.0, base - 1), base + 1
    return None, None


def extract_location_hints(query: str) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    raw_query = str(query or "")
    for match in LOCATION_HINT_RE.finditer(raw_query):
        token = match.group(1).strip()
        if token and token not in seen:
            results.append(token)
            seen.add(token)
    if not results:
        tokens = SIMPLE_KOREAN_TOKEN_RE.findall(normalize_keyword(raw_query))
        for token in tokens[:2]:
            if token and token not in seen:
                results.append(token)
                seen.add(token)
    return results[:5]


def split_candidate_keywords(query: str) -> list[str]:
    cleaned = normalize_keyword(query)
    if not cleaned:
        return []
    parts = re.split(r"\s*(?:,|/|\||vs\.?|대비|와|과|랑|및)\s*", cleaned)
    parts = [p.strip() for p in parts if p.strip()]
    uniq: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part not in seen:
            uniq.append(part)
            seen.add(part)
    return uniq[:5]


def parse_natural_query(query: str) -> ParsedQuery:
    min_pyeong, max_pyeong = parse_pyeong_range(query)
    candidate_keywords = split_candidate_keywords(query)
    compare_mode = any(token in query for token in COMPARE_TOKENS) or len(candidate_keywords) >= 2
    cleaned_query = normalize_keyword(query)
    location_hints = extract_location_hints(query)
    return ParsedQuery(
        raw_query=query,
        cleaned_query=cleaned_query,
        trade_types=parse_trade_types(query),
        min_pyeong=min_pyeong,
        max_pyeong=max_pyeong,
        compare_mode=compare_mode,
        candidate_keywords=candidate_keywords or ([cleaned_query] if cleaned_query else []),
        location_hints=location_hints,
    )


def extract_complex_candidates_from_web(query: str, limit: int = 5) -> list[dict[str, str]]:
    html = _request_text(SEARCH_URL.format(query=urllib.parse.quote(query + DEFAULT_QUERY_SUFFIX)))
    ids: list[str] = []
    seen: set[str] = set()
    patterns = [
        r"https://new\.land\.naver\.com/complexes/(\d+)",
        r"https://new\.land\.naver\.com/houses/(\d+)",
        r"complexNo=(\d+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, html):
            cid = match.group(1)
            if cid not in seen:
                ids.append(cid)
                seen.add(cid)
            if len(ids) >= limit:
                break
        if len(ids) >= limit:
            break
    return [{"complex_id": cid, "source": "web-search", "query": query} for cid in ids]


def fetch_complex_info(complex_id: str) -> dict[str, Any]:
    payload = _request_json(COMPLEX_DETAIL_URL.format(complex_id=complex_id))
    info = payload.get("complexDetail") or payload
    address = " ".join(
        filter(
            None,
            [
                str(info.get("cortarAddress") or "").strip(),
                str(info.get("roadAddressPrefix") or "").strip(),
            ],
        )
    ).strip()
    return {
        "complex_id": complex_id,
        "name": str(info.get("complexName") or info.get("complexNm") or f"단지_{complex_id}"),
        "address": address,
        "household_count": info.get("totalHouseHoldCount") or info.get("houseHoldCount"),
    }


def _tokenize_for_match(text: str) -> list[str]:
    normalized = normalize_keyword(text)
    return [token for token in re.split(r"\s+", normalized) if token and len(token) >= 2]


def _score_candidate(info: dict[str, Any], keyword: str, parsed: ParsedQuery | None) -> int:
    score = 0
    name = str(info.get("name") or "")
    address = str(info.get("address") or "")
    haystack = f"{name} {address}"
    keyword_tokens = _tokenize_for_match(keyword)
    query_tokens = _tokenize_for_match(parsed.cleaned_query if parsed else keyword)

    for token in keyword_tokens:
        if token == name:
            score += 120
        elif token in name:
            score += 45
        elif token in address:
            score += 20
        elif token in haystack:
            score += 10

    for token in query_tokens:
        if token in name:
            score += 12
        elif token in address:
            score += 6

    if parsed:
        for location in parsed.location_hints:
            if location in address:
                score += 30
            elif location in name:
                score += 15

    household_count = info.get("household_count") or 0
    try:
        household_count = int(household_count)
    except Exception:
        household_count = 0
    if household_count >= 300:
        score += 4
    if household_count >= 800:
        score += 4

    return score


def resolve_complex_ids(query: str | None, complex_id: str | None, url: str | None, *, candidate_limit: int = 5) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()

    def _push(value: str | None):
        if value and value not in seen:
            results.append(value)
            seen.add(value)

    _push(complex_id)
    if url:
        _push(NaverURLParser.extract_complex_id(url))
    if query:
        extracted = NaverURLParser.extract_from_text(query)
        for _, cid in extracted:
            _push(cid)
        if not results:
            parsed = parse_natural_query(query)
            ranked_candidates = search_complex_candidates(query, candidate_limit=max(candidate_limit * 2, 6))
            for item in ranked_candidates:
                _push(item.get("complex_id"))
                if len(results) >= candidate_limit:
                    break
            if not results:
                for keyword in parsed.candidate_keywords[:candidate_limit]:
                    for item in extract_complex_candidates_from_web(keyword, limit=candidate_limit):
                        _push(item.get("complex_id"))
                        if len(results) >= candidate_limit:
                            break
                    if len(results) >= candidate_limit:
                        break
    return results[:candidate_limit]


def search_complex_candidates(query: str, *, candidate_limit: int = 5) -> list[dict[str, Any]]:
    parsed = parse_natural_query(query)
    search_terms: list[str] = []
    for value in [parsed.cleaned_query, *parsed.candidate_keywords, *parsed.location_hints]:
        value = str(value or "").strip()
        if value and value not in search_terms:
            search_terms.append(value)

    raw_ids: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for term in search_terms[:6]:
        for item in extract_complex_candidates_from_web(term, limit=max(candidate_limit * 2, 6)):
            cid = str(item.get("complex_id") or "").strip()
            if cid and cid not in seen_ids:
                raw_ids.append((cid, term))
                seen_ids.add(cid)

    scored: list[dict[str, Any]] = []
    for cid, source_term in raw_ids:
        try:
            info = fetch_complex_info(cid)
        except Exception as exc:
            info = {"complex_id": cid, "name": f"단지_{cid}", "address": "", "error": str(exc)}
        score = _score_candidate(info, source_term, parsed)
        scored.append({**info, "match_score": score, "source_term": source_term})

    scored.sort(key=lambda row: (-int(row.get("match_score") or 0), str(row.get("name") or ""), str(row.get("complex_id") or "")))
    return scored[:candidate_limit]


def fetch_articles(complex_id: str, trade_types: list[str], pages: int = 1) -> list[dict[str, Any]]:
    trade_codes = ":".join(TRADE_CODE_MAP[t] for t in trade_types if t in TRADE_CODE_MAP)
    if not trade_codes:
        trade_codes = "A1:B1:B2"
    complex_name = NaverURLParser.fetch_complex_name(complex_id)
    items: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        payload = _request_json(COMPLEX_ARTICLE_URL.format(complex_id=complex_id, trade_codes=trade_codes, page=page))
        article_list = payload.get("articleList") or payload.get("list") or []
        if not article_list:
            break
        for article in article_list:
            trade_type = str(article.get("tradeTypeName") or article.get("tradTpNm") or "").strip()
            normalized = normalize_article_payload(article, complex_name, complex_id, requested_trade_type=trade_type)
            normalized["매물URL"] = get_article_url(complex_id, normalized.get("매물ID", ""), normalized.get("자산유형", "APT"))
            normalized["complex_id"] = complex_id
            items.append(normalized)
    return items


def filter_items(items: list[dict[str, Any]], min_pyeong: float | None, max_pyeong: float | None, limit: int) -> list[dict[str, Any]]:
    filtered = []
    for item in items:
        area = float(item.get("면적(평)") or 0)
        if min_pyeong is not None and area < min_pyeong:
            continue
        if max_pyeong is not None and area > max_pyeong:
            continue
        filtered.append(item)
    filtered.sort(key=lambda row: (row.get("거래유형", ""), PriceConverter.to_int(row.get("매매가") or row.get("보증금") or "0"), row.get("면적(평)", 0)))
    return filtered[:limit]


def build_market_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item.get("거래유형", "기타"), []).append(item)
    summary: dict[str, Any] = {}
    for trade_type, rows in grouped.items():
        prices = [PriceConverter.to_int(r.get("매매가") or r.get("보증금") or "0") for r in rows if (r.get("매매가") or r.get("보증금"))]
        prices = [p for p in prices if p > 0]
        summary[trade_type] = {
            "count": len(rows),
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "avg_price": int(sum(prices) / len(prices)) if prices else None,
            "sample_items": rows[:3],
        }
    return summary


def summarize(items: list[dict[str, Any]]) -> str:
    if not items:
        return "조건에 맞는 매물을 찾지 못했습니다."
    lines = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item.get("거래유형", "기타"), []).append(item)
    for trade_type, rows in grouped.items():
        lines.append(f"[{trade_type}] {len(rows)}건")
        prices = [PriceConverter.to_int(r.get("매매가") or r.get("보증금") or "0") for r in rows if (r.get("매매가") or r.get("보증금"))]
        prices = [p for p in prices if p > 0]
        if prices:
            lines.append(f"- 가격 범위: {PriceConverter.to_string(min(prices))} ~ {PriceConverter.to_string(max(prices))}")
            lines.append(f"- 평균가(단순): {PriceConverter.to_string(int(sum(prices)/len(prices)))}")
        for row in rows[:5]:
            price = row.get("매매가") or row.get("보증금") or "-"
            if trade_type == "월세" and row.get("월세"):
                price = f"{price}/{row.get('월세')}"
            lines.append(
                f"- {row.get('단지명')} | {price} | {row.get('면적(평)', 0)}평 | {row.get('층/방향', '-') or '-'} | {row.get('매물URL', '')}"
            )
    return "\n".join(lines)


def _brief_price(value: int | None) -> str:
    return PriceConverter.to_string(value) if value else "-"


def summarize_comparison(results: list[dict[str, Any]]) -> str:
    if not results:
        return "비교할 단지 결과가 없습니다."
    lines = ["[단지 비교 브리핑]"]
    comparable_rows: list[tuple[str, str, int | None]] = []
    for result in results:
        info = result.get("complex_info", {})
        name = info.get("name", result.get("complex_id"))
        address = info.get("address") or "-"
        lines.append(f"- {name}")
        lines.append(f"  · 주소: {address}")
        for trade_type, meta in result.get("market_summary", {}).items():
            min_price = meta.get("min_price")
            avg_price = meta.get("avg_price")
            max_price = meta.get("max_price")
            lines.append(
                f"  · {trade_type}: {meta.get('count', 0)}건 | 최저 {_brief_price(min_price)} | 평균 {_brief_price(avg_price)} | 최고 {_brief_price(max_price)}"
            )
            comparable_rows.append((name, trade_type, avg_price))

    trade_group: dict[str, list[tuple[str, int]]] = {}
    for name, trade_type, avg_price in comparable_rows:
        if avg_price:
            trade_group.setdefault(trade_type, []).append((name, avg_price))

    for trade_type, rows in trade_group.items():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda x: x[1])
        cheapest_name, cheapest_price = rows[0]
        expensive_name, expensive_price = rows[-1]
        gap = expensive_price - cheapest_price
        if gap > 0:
            lines.append(
                f"- 한줄 해석 ({trade_type}): {cheapest_name} 쪽이 가장 낮고, {expensive_name} 쪽이 가장 높습니다. 평균 기준 격차는 {_brief_price(gap)} 정도입니다."
            )
    return "\n".join(lines)


def run_query(
    *,
    query: str | None,
    complex_id: str | None,
    url: str | None,
    trade_types: list[str] | None,
    pages: int,
    limit: int,
    candidate_limit: int,
    min_pyeong: float | None,
    max_pyeong: float | None,
    compare: bool,
) -> dict[str, Any]:
    parsed = parse_natural_query(query or "") if query else None
    trade_types = list(trade_types or [])
    if not trade_types:
        trade_types = parsed.trade_types if parsed else ["전세"]
    min_pyeong = min_pyeong if min_pyeong is not None else (parsed.min_pyeong if parsed else None)
    max_pyeong = max_pyeong if max_pyeong is not None else (parsed.max_pyeong if parsed else None)

    complex_ids = resolve_complex_ids(query, complex_id, url, candidate_limit=max(1, candidate_limit))
    if not complex_ids:
        raise SearchError("단지 ID를 찾지 못했습니다. 더 구체적인 단지명/지역명을 주거나 단지 URL/ID를 직접 넣어 주세요.")

    compare_mode = compare or bool(parsed and parsed.compare_mode and len(complex_ids) >= 2)
    target_ids = complex_ids[: max(1, candidate_limit if compare_mode else 1)]

    if compare_mode:
        results = []
        for cid in target_ids:
            items = fetch_articles(cid, trade_types, pages=max(1, pages))
            items = filter_items(items, min_pyeong, max_pyeong, max(1, limit))
            results.append(
                {
                    "complex_id": cid,
                    "complex_info": fetch_complex_info(cid),
                    "trade_types": trade_types,
                    "count": len(items),
                    "market_summary": build_market_summary(items),
                    "items": items[:5],
                }
            )
        return {
            "query": query,
            "parsed": asdict(parsed) if parsed else None,
            "compare_mode": True,
            "results": results,
        }

    selected_complex_id = target_ids[0]
    items = fetch_articles(selected_complex_id, trade_types, pages=max(1, pages))
    items = filter_items(items, min_pyeong, max_pyeong, max(1, limit))
    return {
        "query": query,
        "parsed": asdict(parsed) if parsed else None,
        "selected_complex_id": selected_complex_id,
        "complex_info": fetch_complex_info(selected_complex_id),
        "trade_types": trade_types,
        "count": len(items),
        "market_summary": build_market_summary(items),
        "items": items,
    }


def run_self_test() -> int:
    sample = {
        "articleNo": "123456789",
        "tradeTypeName": "전세",
        "dealOrWarrantPrc": "12억 5,000",
        "area1": 84.98,
        "floorInfo": "12/25",
        "direction": "남향",
        "articleFeatureDesc": "역세권, 학군우수",
        "realEstateTypeCode": "APT",
    }
    row = normalize_article_payload(sample, "테스트아파트", "99999", requested_trade_type="전세")
    assert row["단지명"] == "테스트아파트"
    assert row["거래유형"] == "전세"
    assert row["보증금"] == "12억 5,000"
    assert row["면적(평)"] > 0

    parsed = parse_natural_query("잠실 리센츠랑 엘스 전세 비교 30평대")
    assert parsed.compare_mode is True
    assert "전세" in parsed.trade_types
    assert parsed.min_pyeong is not None and parsed.max_pyeong is not None
    assert len(parsed.candidate_keywords) >= 2
    assert "잠실" in parsed.location_hints

    score = _score_candidate({"name": "잠실리센츠", "address": "서울시 송파구 잠실동", "household_count": 5563}, "리센츠", parsed)
    assert score > 0

    print("SELF_TEST_OK")
    print(json.dumps({"sample_row": row, "parsed_query": asdict(parsed), "sample_score": score}, ensure_ascii=False, indent=2)[:1600])
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="네이버 부동산 매물 검색/비교 래퍼")
    p.add_argument("--query", help="자연어 또는 지역/단지 키워드. 예: 잠실 리센츠 전세 30평대, 대치 은마와 래미안대치팰리스 비교")
    p.add_argument("--complex-id", help="네이버 부동산 단지 ID")
    p.add_argument("--url", help="네이버 부동산 단지/매물 URL")
    p.add_argument("--trade-types", default="", help="쉼표 구분 거래 유형. 비우면 query에서 추론하고, 없으면 전세")
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--candidate-limit", type=int, default=3)
    p.add_argument("--min-pyeong", type=float)
    p.add_argument("--max-pyeong", type=float)
    p.add_argument("--list-candidates", action="store_true", help="매물 조회 대신 단지 후보만 출력")
    p.add_argument("--compare", action="store_true", help="후보 상위 단지들을 비교 모드로 조회")
    p.add_argument("--parse-only", action="store_true", help="자연어 파싱 결과만 출력")
    p.add_argument("--json", action="store_true")
    p.add_argument("--self-test", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        return run_self_test()

    parsed = parse_natural_query(args.query or "") if args.query else None
    if args.parse_only:
        print(json.dumps(asdict(parsed) if parsed else {}, ensure_ascii=False, indent=2))
        return 0

    trade_types = [token.strip() for token in str(args.trade_types).split(",") if token.strip()]

    if args.list_candidates:
        if not args.query:
            raise SystemExit("--list-candidates 는 --query 와 함께 사용하세요.")
        candidates = search_complex_candidates(args.query, candidate_limit=max(1, args.candidate_limit))
        print(json.dumps({"query": args.query, "parsed": asdict(parsed), "candidates": candidates}, ensure_ascii=False, indent=2))
        return 0

    output = run_query(
        query=args.query,
        complex_id=args.complex_id,
        url=args.url,
        trade_types=trade_types,
        pages=max(1, args.pages),
        limit=max(1, args.limit),
        candidate_limit=max(1, args.candidate_limit),
        min_pyeong=args.min_pyeong,
        max_pyeong=args.max_pyeong,
        compare=bool(args.compare),
    )
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if output.get("compare_mode"):
            print(summarize_comparison(output.get("results", [])))
        else:
            print(summarize(output.get("items", [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
