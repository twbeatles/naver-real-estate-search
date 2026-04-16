from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[3]
UPSTREAM = WORKSPACE / "tmp" / "naverland-scrapper"
SRC_ROOT = UPSTREAM / "src"
if str(UPSTREAM) not in sys.path:
    sys.path.insert(0, str(UPSTREAM))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

UPSTREAM_IMPORT_ERROR: Exception | None = None
try:
    from src.core.parser import NaverURLParser
    from src.utils.helpers import PriceConverter, get_article_url
    from src.utils.runtime_playwright import configure_playwright_browsers_path
except Exception as exc:
    UPSTREAM_IMPORT_ERROR = exc

    class NaverURLParser:
        @staticmethod
        def extract_from_text(text: str) -> list[tuple[str, str]]:
            pairs: list[tuple[str, str]] = []
            for match in URL_COMPLEX_ID_RE.finditer(text or ""):
                cid = match.group(1) or match.group(2)
                if cid:
                    pairs.append(("", cid))
            for match in RAW_COMPLEX_ID_RE.finditer(text or ""):
                cid = match.group(1)
                if cid:
                    pairs.append(("", cid))
            return pairs

    class PriceConverter:
        @staticmethod
        def to_int(value: Any) -> int:
            raw = str(value or "").strip()
            if not raw:
                return 0
            digits = re.sub(r"[^0-9]", "", raw)
            return int(digits) if digits else 0

    def get_article_url(complex_id: str, article_id: str, real_estate_type: str = "APT") -> str:
        article = str(article_id or "").strip()
        if not article:
            return ""
        return f"https://new.land.naver.com/articles/{article}?complexNo={complex_id}&realEstateType={real_estate_type}"

    def configure_playwright_browsers_path() -> None:
        return None

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DEFAULT_PROFILE_DIR = WORKSPACE / "playwright_profile" / "naver-real-estate-search"
DEFAULT_STORAGE_STATE = WORKSPACE / "skills" / "naver-real-estate-search" / "data" / "browser-session.json"
DEFAULT_HOME_URL = "https://new.land.naver.com/"
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
RAW_COMPLEX_ID_RE = re.compile(r"(?:complex(?:\s*id|no)?|단지(?:\s*id)?|id)\s*[:=#-]?\s*(\d{3,10})", re.I)
URL_COMPLEX_ID_RE = re.compile(r"new\.land\.naver\.com/(?:complexes|houses)/(\d+)|complexNo=(\d+)", re.I)


def extract_complex_ids(text: str) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for _, cid in NaverURLParser.extract_from_text(text or ""):
        if cid and cid not in seen:
            ids.append(cid)
            seen.add(cid)
    for match in RAW_COMPLEX_ID_RE.finditer(text or ""):
        cid = match.group(1)
        if cid and cid not in seen:
            ids.append(cid)
            seen.add(cid)
    for match in URL_COMPLEX_ID_RE.finditer(text or ""):
        cid = match.group(1) or match.group(2)
        if cid and cid not in seen:
            ids.append(cid)
            seen.add(cid)
    text_clean = str(text or "").strip()
    if re.fullmatch(r"\d{3,10}", text_clean) and text_clean not in seen:
        ids.append(text_clean)
    return ids


def canonical_complex_url(complex_id: str) -> str:
    return f"https://new.land.naver.com/complexes/{complex_id}"


def _launch_context(profile_dir: Path, *, headless: bool):
    configure_playwright_browsers_path()
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        str(profile_dir),
        headless=headless,
        viewport={"width": 1440, "height": 1000},
        args=["--disable-blink-features=AutomationControlled"],
    )
    return pw, context


def browser_capture(*, url: str | None, profile_dir: Path, storage_state_path: Path, wait_seconds: int, headless: bool) -> dict[str, Any]:
    profile_dir.mkdir(parents=True, exist_ok=True)
    storage_state_path.parent.mkdir(parents=True, exist_ok=True)
    pw, context = _launch_context(profile_dir, headless=headless)
    page = context.pages[0] if context.pages else context.new_page()
    target = url or DEFAULT_HOME_URL
    try:
        page.goto(target, wait_until="domcontentloaded", timeout=45000)
    except PlaywrightTimeoutError:
        pass
    if wait_seconds > 0:
        try:
            page.wait_for_timeout(wait_seconds * 1000)
        except Exception:
            time.sleep(wait_seconds)
    current_url = page.url
    html = page.content()
    ids = extract_complex_ids("\n".join([target, current_url]))
    if not ids:
        ids = extract_complex_ids(html[:40000])
    title = page.title()
    payload = {
        "captured_at": int(time.time()),
        "requested_url": target,
        "current_url": current_url,
        "title": title,
        "detected_complex_ids": ids,
        "canonical_complex_urls": [canonical_complex_url(cid) for cid in ids],
        "profile_dir": str(profile_dir),
        "storage_state_path": str(storage_state_path),
    }
    context.storage_state(path=str(storage_state_path))
    context.close()
    pw.stop()
    return payload


def browser_fetch(*, complex_id: str, profile_dir: Path, headless: bool, trade_types: list[str], page_count: int) -> dict[str, Any]:
    profile_dir.mkdir(parents=True, exist_ok=True)
    pw, context = _launch_context(profile_dir, headless=headless)
    page = context.pages[0] if context.pages else context.new_page()
    complex_url = canonical_complex_url(complex_id)
    try:
        page.goto(complex_url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1500)
    except PlaywrightTimeoutError:
        pass

    def _fetch_json(api_url: str) -> Any:
        script = """
        async (apiUrl) => {
          const res = await fetch(apiUrl, {
            credentials: 'include',
            headers: {
              'accept': 'application/json, text/plain, */*',
              'x-requested-with': 'XMLHttpRequest'
            }
          });
          const text = await res.text();
          return {ok: res.ok, status: res.status, text};
        }
        """
        result = page.evaluate(script, api_url)
        text = result.get("text") or ""
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {"raw_text": text[:2000]}
        return {"ok": result.get("ok"), "status": result.get("status"), "body": parsed}

    detail = _fetch_json(COMPLEX_DETAIL_URL.format(complex_id=complex_id))
    trade_codes = ":".join(TRADE_CODE_MAP[t] for t in trade_types if t in TRADE_CODE_MAP) or "A1:B1:B2"
    articles: list[dict[str, Any]] = []
    article_statuses: list[dict[str, Any]] = []
    for page_no in range(1, max(1, page_count) + 1):
        article_url = COMPLEX_ARTICLE_URL.format(complex_id=complex_id, trade_codes=trade_codes, page=page_no)
        fetched = _fetch_json(article_url)
        article_statuses.append({"page": page_no, "status": fetched.get("status"), "ok": fetched.get("ok")})
        body = fetched.get("body") or {}
        raw_list = body.get("articleList") or body.get("list") or []
        if not raw_list:
            continue
        for row in raw_list[:20]:
            price = row.get("dealOrWarrantPrc") or row.get("price") or row.get("formattedPrice") or "-"
            monthly = row.get("rentPrc") or row.get("rentPrice") or ""
            area = row.get("area1") or row.get("area2") or row.get("spc1") or row.get("spc2")
            article_no = str(row.get("articleNo") or row.get("atclNo") or "")
            asset_type = str(row.get("realEstateTypeCode") or row.get("rletTpCd") or "APT")
            articles.append(
                {
                    "article_no": article_no,
                    "trade_type": row.get("tradeTypeName") or row.get("tradTpNm"),
                    "price_text": price,
                    "price_int": PriceConverter.to_int(str(price or "0")),
                    "monthly_rent": monthly,
                    "area": area,
                    "floor_info": row.get("floorInfo"),
                    "direction": row.get("direction"),
                    "article_url": get_article_url(complex_id, article_no, asset_type) if article_no else None,
                }
            )
    payload = {
        "kind": "browser-assisted-fetch",
        "captured_at": int(time.time()),
        "complex_id": complex_id,
        "complex_url": complex_url,
        "profile_dir": str(profile_dir),
        "detail_status": {"status": detail.get("status"), "ok": detail.get("ok")},
        "detail": detail.get("body"),
        "article_statuses": article_statuses,
        "articles": articles,
        "article_count": len(articles),
    }
    context.close()
    pw.stop()
    return payload


def resolve_direct_input(text: str | None, complex_id: str | None, url: str | None) -> dict[str, Any]:
    parts = [str(x or "") for x in [text, complex_id, url] if str(x or "").strip()]
    merged = "\n".join(parts)
    ids = extract_complex_ids(merged)
    chosen = str(complex_id or "").strip() or (ids[0] if ids else "")
    return {
        "input": text,
        "explicit_complex_id": complex_id,
        "explicit_url": url,
        "detected_complex_ids": ids,
        "selected_complex_id": chosen or None,
        "canonical_complex_url": canonical_complex_url(chosen) if chosen else None,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="네이버 부동산 local browser / Playwright 보조 헬퍼")
    sub = p.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture", help="브라우저를 열어 현재 세션/URL에서 complex ID를 잡는다")
    capture.add_argument("--url")
    capture.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR))
    capture.add_argument("--storage-state", default=str(DEFAULT_STORAGE_STATE))
    capture.add_argument("--wait-seconds", type=int, default=12)
    capture.add_argument("--headless", action="store_true")

    resolve = sub.add_parser("resolve", help="텍스트/URL/ID에서 direct complex ID와 canonical URL을 정리한다")
    resolve.add_argument("--text")
    resolve.add_argument("--complex-id")
    resolve.add_argument("--url")

    fetch = sub.add_parser("fetch", help="브라우저 세션 안에서 same-origin fetch로 detail/articles를 가져온다")
    fetch.add_argument("--complex-id")
    fetch.add_argument("--url")
    fetch.add_argument("--text")
    fetch.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR))
    fetch.add_argument("--headless", action="store_true")
    fetch.add_argument("--trade-types", default="전세")
    fetch.add_argument("--pages", type=int, default=1)

    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "resolve":
        print(json.dumps(resolve_direct_input(args.text, args.complex_id, args.url), ensure_ascii=False, indent=2))
        return 0
    if args.command == "capture":
        payload = browser_capture(
            url=args.url,
            profile_dir=Path(args.profile_dir),
            storage_state_path=Path(args.storage_state),
            wait_seconds=max(0, int(args.wait_seconds)),
            headless=bool(args.headless),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "fetch":
        resolved = resolve_direct_input(args.text, args.complex_id, args.url)
        selected = resolved.get("selected_complex_id")
        if not selected:
            raise SystemExit("complex ID를 찾지 못했습니다. --complex-id / --url / --text 중 하나에 direct 단서를 넣어 주세요.")
        trade_types = [token.strip() for token in str(args.trade_types or "").split(",") if token.strip()]
        payload = browser_fetch(
            complex_id=str(selected),
            profile_dir=Path(args.profile_dir),
            headless=bool(args.headless),
            trade_types=trade_types or ["전세"],
            page_count=max(1, int(args.pages)),
        )
        payload["resolved"] = resolved
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
