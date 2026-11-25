"""Compare a dated prospective ZPTA candidate against a separate public anchor.

Read-only, source-quality gate. A single matching anchor does not verify the
full corporate-action-adjusted history or executable OTC bid/ask liquidity.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def reconcile(snapshot, *, anchor_date, anchor_close, anchor_volume, anchor_source,
              close_tolerance_pct=0.5, volume_tolerance_pct=5.0):
    if snapshot.get("symbol") != "ZPTA":
        raise ValueError("Unexpected symbol")
    if snapshot.get("as_of") != anchor_date:
        raise ValueError("Anchor date mismatch")
    if not anchor_source.strip() or anchor_source == snapshot.get("source"):
        raise ValueError("Require a distinct, named reference source")
    if not math.isfinite(anchor_close) or anchor_close <= 0 or anchor_volume < 0:
        raise ValueError("Invalid anchor values")
    if not all(math.isfinite(x) and x >= 0 for x in
               (close_tolerance_pct, volume_tolerance_pct)):
        raise ValueError("Invalid tolerance")
    price = float(snapshot["reference_close"])
    volume = float(snapshot["reference_volume"])
    if not math.isfinite(price) or price <= 0 or not math.isfinite(volume) or volume < 0:
        raise ValueError("Invalid candidate values")
    close_diff = abs(price/anchor_close-1)*100
    volume_diff = (abs(volume/anchor_volume-1)*100 if anchor_volume > 0
                   else (0.0 if volume == 0 else float("inf")))
    status = ("SINGLE_DATE_ANCHOR_WITHIN_TOLERANCE_NOT_FULLY_VERIFIED"
              if close_diff <= close_tolerance_pct and
                 volume_diff <= volume_tolerance_pct
              else "SOURCE_MISMATCH_DO_NOT_PROMOTE")
    return {
        "symbol": "ZPTA",
        "as_of": anchor_date,
        "candidate_source": snapshot["source"],
        "anchor_source": anchor_source,
        "candidate_close": price,
        "anchor_close": anchor_close,
        "close_difference_pct": round(close_diff, 4),
        "candidate_volume": volume,
        "anchor_volume": anchor_volume,
        "volume_difference_pct": round(volume_diff, 4),
        "candidate_turnover_proxy": round(price*volume, 2),
        "anchor_turnover_proxy": round(anchor_close*anchor_volume, 2),
        "close_tolerance_pct": close_tolerance_pct,
        "volume_tolerance_pct": volume_tolerance_pct,
        "source_status": status,
        "full_history_split_adjustment_verified": False,
        "broker_bid_ask_and_order_fill_verified": False,
        "real_money_trading_allowed": False,
        "warning": ("A mismatch may reflect delayed/partial provider publication "
                    "or differing venue coverage; do not select the favorable "
                    "number or backfill a prediction after the fact."),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot", type=Path)
    p.add_argument("--anchor-date", required=True)
    p.add_argument("--anchor-close", required=True, type=float)
    p.add_argument("--anchor-volume", required=True, type=int)
    p.add_argument("--anchor-source", required=True)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    d = reconcile(
        json.loads(args.snapshot.read_text(encoding="utf-8")),
        anchor_date=args.anchor_date, anchor_close=args.anchor_close,
        anchor_volume=args.anchor_volume, anchor_source=args.anchor_source)
    payload = json.dumps(d, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as f:
            f.write(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
