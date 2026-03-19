from __future__ import annotations

import argparse
import json
from typing import Any

from search_real_estate import PriceConverter, run_query, search_complex_candidates


def _fmt_price(value: int | None) -> str:
    return PriceConverter.to_string(value) if value else "-"


def _pick_headline(meta: dict[str, Any], trade_type: str) -> str:
    count = int(meta.get("count") or 0)
    if count == 0:
        return f"{trade_type} 매물이 거의 안 잡힙니다."
    if count <= 3:
        return f"{trade_type} 매물이 많지는 않지만 확인 가능한 건은 있습니다."
    if count <= 10:
        return f"{trade_type} 매물이 어느 정도 보입니다."
    return f"{trade_type} 매물이 비교적 넉넉하게 잡힙니다."


def brief_single(payload: dict[str, Any]) -> str:
    info = payload.get("complex_info") or {}
    lines = [f"{info.get('name', payload.get('selected_complex_id'))} 브리핑"]
    if info.get("address"):
        lines.append(f"- 위치: {info['address']}")
    if payload.get("parsed", {}).get("min_pyeong") or payload.get("parsed", {}).get("max_pyeong"):
        lines.append(
            f"- 평형 필터: {payload.get('parsed', {}).get('min_pyeong', '-') }~{payload.get('parsed', {}).get('max_pyeong', '-') }평"
        )
    summary = payload.get("market_summary") or {}
    if not summary:
        lines.append("- 조건에 맞는 매물이 아직 잡히지 않았습니다.")
        return "\n".join(lines)
    for trade_type, meta in summary.items():
        lines.append(f"- {trade_type}: {meta.get('count', 0)}건")
        lines.append(f"  · {_pick_headline(meta, trade_type)}")
        lines.append(
            f"  · 가격대: 최저 {_fmt_price(meta.get('min_price'))} / 평균 {_fmt_price(meta.get('avg_price'))} / 최고 {_fmt_price(meta.get('max_price'))}"
        )
    for row in payload.get("items", [])[:3]:
        price = row.get("매매가") or row.get("보증금") or "-"
        if row.get("거래유형") == "월세" and row.get("월세"):
            price = f"{price}/{row.get('월세')}"
        lines.append(f"- 대표 매물: {price}, {row.get('면적(평)', 0)}평, {row.get('층/방향', '-') or '-'}")
        if row.get("특징"):
            lines.append(f"  · 포인트: {row['특징']}")
        if row.get("매물URL"):
            lines.append(f"  · 링크: {row['매물URL']}")
    return "\n".join(lines)


def brief_compare(payload: dict[str, Any]) -> str:
    results = payload.get("results") or []
    lines = ["단지 비교 브리핑"]
    trade_best: dict[str, tuple[str, int]] = {}
    trade_worst: dict[str, tuple[str, int]] = {}
    for result in results:
        info = result.get("complex_info") or {}
        name = info.get("name", result.get("complex_id"))
        address = info.get("address") or "-"
        lines.append(f"- {name} ({address})")
        summary = result.get("market_summary") or {}
        if not summary:
            lines.append("  · 조건에 맞는 매물이 거의 안 보입니다.")
            continue
        for trade_type, meta in summary.items():
            avg_price = meta.get("avg_price")
            lines.append(
                f"  · {trade_type}: {meta.get('count', 0)}건 / 최저 {_fmt_price(meta.get('min_price'))} / 평균 {_fmt_price(avg_price)} / 최고 {_fmt_price(meta.get('max_price'))}"
            )
            if avg_price:
                if trade_type not in trade_best or avg_price < trade_best[trade_type][1]:
                    trade_best[trade_type] = (name, avg_price)
                if trade_type not in trade_worst or avg_price > trade_worst[trade_type][1]:
                    trade_worst[trade_type] = (name, avg_price)
    for trade_type in sorted(trade_best):
        best_name, best_price = trade_best[trade_type]
        worst_name, worst_price = trade_worst[trade_type]
        gap = worst_price - best_price
        if gap > 0:
            lines.append(
                f"- 해석: {trade_type} 기준으로는 {best_name} 쪽 평균이 더 낮고, {worst_name} 쪽이 더 높습니다. 차이는 대략 {_fmt_price(gap)}입니다."
            )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="네이버 부동산 채팅형 브리핑 래퍼")
    p.add_argument("--query", help="자연어 질의")
    p.add_argument("--complex-id")
    p.add_argument("--url")
    p.add_argument("--trade-types", default="")
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--candidate-limit", type=int, default=3)
    p.add_argument("--min-pyeong", type=float)
    p.add_argument("--max-pyeong", type=float)
    p.add_argument("--list-candidates", action="store_true")
    p.add_argument("--compare", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.list_candidates:
        if not args.query:
            raise SystemExit("--list-candidates 는 --query 와 함께 사용하세요.")
        candidates = search_complex_candidates(args.query, candidate_limit=max(1, args.candidate_limit))
        if args.json:
            print(json.dumps(candidates, ensure_ascii=False, indent=2))
        else:
            lines = ["후보 단지"]
            for idx, row in enumerate(candidates, start=1):
                lines.append(
                    f"- {idx}. {row.get('name')} | {row.get('address') or '-'} | ID {row.get('complex_id')} | score {row.get('match_score', '-') }"
                )
            print("\n".join(lines))
        return 0

    trade_types = [token.strip() for token in str(args.trade_types).split(",") if token.strip()]
    payload = run_query(
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
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(brief_compare(payload) if payload.get("compare_mode") else brief_single(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
