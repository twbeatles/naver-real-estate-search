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
    "보여줘", "조회", "검색", "추천", "아파트", "빌라", "오피스텔", "매매", "전세", "월세", "실거래가", "단지",
]


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
    value = text.strip()
    for token in STOPWORDS:
        value = value.replace(token, " ")
    value = re.sub(r"\b\d+\s*평(?:대|형)?\b", " ", value)
    value = re.sub(r"\b\d+\s*(?:평|형)\b", " ", value)
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
    compare_mode = any(token in query for token in ["비교", "대비"]) or len(candidate_keywords) >= 2
    cleaned_query = normalize_keyword(query)
    return ParsedQuery(
        raw_query=query,
        cleaned_query=cleaned_query,
        trade_types=parse_trade_types(query),
        min_pyeong=min_pyeong,
        max_pyeong=max_pyeong,
        compare_mode=compare_mode,
        candidate_keywords=candidate_keywords or ([cleaned_query] if cleaned_query else []),
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
    return {
        "complex_id": complex_id,
        "name": str(info.get("complexName") or info.get("complexNm") or f"단지_{complex_id}"),
        "address": " ".join(filter(None, [str(info.get("cortarAddress") or "").strip(), str(info.get("roadAddressPrefix") or "").strip()] )).strip(),
        "household_count": info.get("totalHouseHoldCount") or info.get("houseHoldCount"),
    }


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
            for keyword in parsed.candidate_keywords[:candidate_limit]:
                for item in extract_complex_candidates_from_web(keyword, limit=candidate_limit):
                    _push(item.get("complex_id"))
                    if len(results) >= candidate_limit:
                        break
                if len(results) >= candidate_limit:
                    break
    return results


def search_complex_candidates(query: str, *, candidate_limit: int = 5) -> list[dict[str, Any]]:
    parsed = parse_natural_query(query)
    ids = resolve_complex_ids(query, None, None, candidate_limit=candidate_limit)
    candidates: list[dict[str, Any]] = []
    for cid in ids[:candidate_limit]:
        try:
            info = fetch_complex_info(cid)
        except Exception as exc:
            info = {"complex_id": cid, "name": f"단지_{cid}", "address": "", "error": str(exc)}
        candidates.append(info)
    return candidates


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


def summarize_comparison(results: list[dict[str, Any]]) -> str:
    if not results:
        return "비교할 단지 결과가 없습니다."
    lines = ["[단지 비교 요약]"]
    for result in results:
        info = result.get("complex_info", {})
        lines.append(f"- {info.get('name', result.get('complex_id'))} (ID {result.get('complex_id')})")
        lines.append(f"  주소: {info.get('address') or '-'}")
        for trade_type, meta in result.get("market_summary", {}).items():
            min_price = PriceConverter.to_string(meta["min_price"]) if meta.get("min_price") else "-"
            max_price = PriceConverter.to_string(meta["max_price"]) if meta.get("max_price") else "-"
            avg_price = PriceConverter.to_string(meta["avg_price"]) if meta.get("avg_price") else "-"
            lines.append(f"  · {trade_type}: {meta.get('count', 0)}건 | 최저 {min_price} | 평균 {avg_price} | 최고 {max_price}")
    return "\n".join(lines)


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

    print("SELF_TEST_OK")
    print(json.dumps({"sample_row": row, "parsed_query": asdict(parsed)}, ensure_ascii=False, indent=2)[:1200])
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
    if not trade_types:
        trade_types = parsed.trade_types if parsed else ["전세"]

    min_pyeong = args.min_pyeong if args.min_pyeong is not None else (parsed.min_pyeong if parsed else None)
    max_pyeong = args.max_pyeong if args.max_pyeong is not None else (parsed.max_pyeong if parsed else None)

    if args.list_candidates:
        if not args.query:
            raise SystemExit("--list-candidates 는 --query 와 함께 사용하세요.")
        candidates = search_complex_candidates(args.query, candidate_limit=max(1, args.candidate_limit))
        print(json.dumps({"query": args.query, "parsed": asdict(parsed), "candidates": candidates}, ensure_ascii=False, indent=2))
        return 0

    complex_ids = resolve_complex_ids(args.query, args.complex_id, args.url, candidate_limit=max(1, args.candidate_limit))
    if not complex_ids:
        raise SystemExit("단지 ID를 찾지 못했습니다. 더 구체적인 단지명/지역명을 주거나 단지 URL/ID를 직접 넣어 주세요.")

    compare_mode = args.compare or bool(parsed and parsed.compare_mode and len(complex_ids) >= 2)
    target_ids = complex_ids[: max(1, args.candidate_limit if compare_mode else 1)]

    if compare_mode:
        results = []
        for cid in target_ids:
            items = fetch_articles(cid, trade_types, pages=max(1, args.pages))
            items = filter_items(items, min_pyeong, max_pyeong, max(1, args.limit))
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
        payload = {
            "query": args.query,
            "parsed": asdict(parsed) if parsed else None,
            "compare_mode": True,
            "results": results,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(summarize_comparison(results))
        return 0

    selected_complex_id = target_ids[0]
    items = fetch_articles(selected_complex_id, trade_types, pages=max(1, args.pages))
    items = filter_items(items, min_pyeong, max_pyeong, max(1, args.limit))

    output = {
        "query": args.query,
        "parsed": asdict(parsed) if parsed else None,
        "selected_complex_id": selected_complex_id,
        "complex_info": fetch_complex_info(selected_complex_id),
        "trade_types": trade_types,
        "count": len(items),
        "market_summary": build_market_summary(items),
        "items": items,
    }
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(summarize(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
