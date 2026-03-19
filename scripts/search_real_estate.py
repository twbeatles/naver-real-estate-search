from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
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


class SearchError(RuntimeError):
    pass


def _request_json(url: str, *, referer: str = "https://new.land.naver.com/") -> Any:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Referer", referer)
    req.add_header("Accept", "application/json, text/plain, */*")
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        if exc.code == 429:
            raise SearchError("네이버 부동산 API가 429(요청 제한)를 반환했습니다. 잠시 후 다시 시도하거나, 단지 URL/ID를 직접 제공해 주세요.")
        raise SearchError(f"네이버 부동산 API 호출 실패: HTTP {exc.code} {body[:200]}")
    except Exception as exc:
        raise SearchError(f"네이버 부동산 API 호출 실패: {exc}") from exc


def _request_text(url: str) -> str:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read().decode("utf-8", errors="ignore")


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
    return [{"complex_id": cid, "source": "web-search"} for cid in ids]


def resolve_complex_ids(query: str | None, complex_id: str | None, url: str | None) -> list[str]:
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
            for item in extract_complex_candidates_from_web(query):
                _push(item.get("complex_id"))
    return results


def fetch_complex_name(complex_id: str) -> str:
    return NaverURLParser.fetch_complex_name(complex_id)


def fetch_articles(complex_id: str, trade_types: list[str], pages: int = 1) -> list[dict[str, Any]]:
    trade_codes = ":".join(TRADE_CODE_MAP[t] for t in trade_types if t in TRADE_CODE_MAP)
    if not trade_codes:
        trade_codes = "A1:B1:B2"
    complex_name = fetch_complex_name(complex_id)
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


def summarize(items: list[dict[str, Any]]) -> str:
    if not items:
        return "조건에 맞는 매물을 찾지 못했습니다."
    lines = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item.get("거래유형", "기타"), []).append(item)
    for trade_type, rows in grouped.items():
        lines.append(f"[{trade_type}] {len(rows)}건")
        prices = [PriceConverter.to_int(r.get("매매가") or r.get("보증금") or "0") for r in rows]
        if prices:
            lines.append(f"- 가격 범위: {PriceConverter.to_string(min(prices))} ~ {PriceConverter.to_string(max(prices))}")
        for row in rows[:5]:
            price = row.get("매매가") or row.get("보증금") or "-"
            if trade_type == "월세" and row.get("월세"):
                price = f"{price}/{row.get('월세')}"
            lines.append(
                f"- {row.get('단지명')} | {price} | {row.get('면적(평)', 0)}평 | {row.get('층/방향', '-') or '-'} | {row.get('매물URL', '')}"
            )
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
    print("SELF_TEST_OK")
    print(json.dumps(row, ensure_ascii=False, indent=2)[:800])
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="네이버 부동산 매물 검색 최소 래퍼")
    p.add_argument("--query", help="지역/단지 키워드. 예: 강남 아파트 전세, 대치동 아파트")
    p.add_argument("--complex-id", help="네이버 부동산 단지 ID")
    p.add_argument("--url", help="네이버 부동산 단지/매물 URL")
    p.add_argument("--trade-types", default="전세", help="쉼표 구분 거래 유형. 예: 매매,전세,월세")
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--min-pyeong", type=float)
    p.add_argument("--max-pyeong", type=float)
    p.add_argument("--json", action="store_true")
    p.add_argument("--self-test", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        return run_self_test()

    trade_types = [token.strip() for token in str(args.trade_types).split(",") if token.strip()]
    complex_ids = resolve_complex_ids(args.query, args.complex_id, args.url)
    if not complex_ids:
        raise SystemExit("단지 ID를 찾지 못했습니다. 더 구체적인 단지명/지역명을 주거나 단지 URL/ID를 직접 넣어 주세요.")

    selected_complex_id = complex_ids[0]
    items = fetch_articles(selected_complex_id, trade_types, pages=max(1, args.pages))
    items = filter_items(items, args.min_pyeong, args.max_pyeong, max(1, args.limit))

    output = {
        "query": args.query,
        "selected_complex_id": selected_complex_id,
        "trade_types": trade_types,
        "count": len(items),
        "items": items,
    }
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(summarize(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
