from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from search_real_estate import WATCH_STATE_FILE, PriceConverter, run_query


def _load_rules() -> dict[str, Any]:
    if WATCH_STATE_FILE.exists():
        return json.loads(WATCH_STATE_FILE.read_text(encoding="utf-8"))
    return {"rules": []}


def _save_rules(data: dict[str, Any]) -> None:
    WATCH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    WATCH_STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_rule(args: argparse.Namespace) -> int:
    data = _load_rules()
    rule = {
        "name": args.name,
        "query": args.query,
        "complex_id": args.complex_id,
        "url": args.url,
        "trade_types": [token.strip() for token in str(args.trade_types or "").split(",") if token.strip()],
        "target_max_price": args.target_max_price,
        "pages": args.pages,
        "limit": args.limit,
        "candidate_limit": args.candidate_limit,
        "min_pyeong": args.min_pyeong,
        "max_pyeong": args.max_pyeong,
    }
    data.setdefault("rules", []).append(rule)
    _save_rules(data)
    print(json.dumps({"saved": True, "rule": rule}, ensure_ascii=False, indent=2))
    return 0


def list_rules() -> int:
    print(json.dumps(_load_rules(), ensure_ascii=False, indent=2))
    return 0


def check_rules(args: argparse.Namespace) -> int:
    data = _load_rules()
    alerts = []
    for rule in data.get("rules", []):
        payload = run_query(
            query=rule.get("query"),
            complex_id=rule.get("complex_id"),
            url=rule.get("url"),
            trade_types=rule.get("trade_types") or [],
            pages=max(1, int(rule.get("pages") or 1)),
            limit=max(1, int(rule.get("limit") or 10)),
            candidate_limit=max(1, int(rule.get("candidate_limit") or 1)),
            min_pyeong=rule.get("min_pyeong"),
            max_pyeong=rule.get("max_pyeong"),
            compare=False,
        )
        threshold = rule.get("target_max_price")
        matches = []
        for item in payload.get("items", []):
            price = PriceConverter.to_int(item.get("매매가") or item.get("보증금") or "0")
            if threshold and price and price <= threshold:
                matches.append({
                    "price": price,
                    "price_text": PriceConverter.to_string(price),
                    "complex_name": item.get("단지명"),
                    "article_url": item.get("매물URL"),
                    "area_pyeong": item.get("면적(평)"),
                    "trade_type": item.get("거래유형"),
                })
        alerts.append({
            "rule": rule,
            "matched": matches,
            "matched_count": len(matches),
        })
    if args.json:
        print(json.dumps({"alerts": alerts}, ensure_ascii=False, indent=2))
    else:
        lines = ["가격 감시 점검"]
        for row in alerts:
            rule = row["rule"]
            lines.append(f"- {rule.get('name')}: {row.get('matched_count', 0)}건")
            for matched in row.get("matched", [])[:5]:
                lines.append(
                    f"  · {matched.get('complex_name')} {matched.get('trade_type')} {matched.get('price_text')} / {matched.get('area_pyeong')}평 / {matched.get('article_url')}"
                )
        print("\n".join(lines))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="네이버 부동산 가격 감시 초안")
    sub = p.add_subparsers(dest="cmd", required=True)

    add_p = sub.add_parser("add")
    add_p.add_argument("--name", required=True)
    add_p.add_argument("--query")
    add_p.add_argument("--complex-id")
    add_p.add_argument("--url")
    add_p.add_argument("--trade-types", default="")
    add_p.add_argument("--target-max-price", type=int, required=True, help="정수 가격 기준. 예: 950000000")
    add_p.add_argument("--pages", type=int, default=1)
    add_p.add_argument("--limit", type=int, default=10)
    add_p.add_argument("--candidate-limit", type=int, default=1)
    add_p.add_argument("--min-pyeong", type=float)
    add_p.add_argument("--max-pyeong", type=float)

    sub.add_parser("list")
    check_p = sub.add_parser("check")
    check_p.add_argument("--json", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.cmd == "add":
        return add_rule(args)
    if args.cmd == "list":
        return list_rules()
    if args.cmd == "check":
        return check_rules(args)
    raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())
