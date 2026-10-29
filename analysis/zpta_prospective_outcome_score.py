"""Score frozen daily ZPTA research candidates ONLY after future sessions close.

This module never changes original signal flags, predicts no future outcome,
and does not assume a broker fill at the opening print or intraday low.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from analysis.zpta_intraday_recovery import load_daily


def score_snapshot(snapshot, bars, one_way_cost=.01):
    if snapshot.get("symbol") != "ZPTA":
        raise ValueError("Wrong symbol")
    if snapshot.get("snapshot_type") != "SAME_DAY_POST_CLOSE_CANDIDATE":
        raise ValueError("Not a contemporaneously frozen snapshot")
    # A dated source mismatch is a hard research-quality block, even if a
    # subsequent fetch happens to reproduce the original unverified bar.
    # Do not turn a mismatched signal into a validated forward return.
    if snapshot.get("independent_source_quality_status") == "SOURCE_MISMATCH_DO_NOT_PROMOTE":
        raise ValueError("SOURCE_MISMATCH_DO_NOT_SCORE: reconcile frozen signal source")
    if not 0 <= one_way_cost < .5:
        raise ValueError("Invalid cost")
    dates = [b["date"] for b in bars]
    if dates != sorted(set(dates)):
        raise ValueError("Unsorted or duplicate daily dates")
    as_of = snapshot["as_of"]
    if as_of not in dates:
        raise ValueError("Missing original as-of bar")
    i = dates.index(as_of)
    original = bars[i]
    if not math.isclose(original["close"], snapshot["reference_close"], rel_tol=1e-8) or \
       int(original["volume"]) != int(snapshot["reference_volume"]):
        raise ValueError("FROZEN_SIGNAL_BAR_REVISED: reconcile source before scoring")
    out = {}
    for h in (1, 3, 5):
        if i+h >= len(bars):
            out[f"{h}d"] = None
            continue
        entry = bars[i+1]["open"]*(1+one_way_cost)
        exit_px = bars[i+h]["close"]*(1-one_way_cost)
        low = min(b["low"] for b in bars[i+1:i+h+1])
        out[f"{h}d"] = {
            "entry_session": bars[i+1]["date"],
            "exit_session": bars[i+h]["date"],
            "entry_open_print": bars[i+1]["open"],
            "exit_close_print": bars[i+h]["close"],
            "hypothetical_net_pct": round((exit_px/entry-1)*100, 4),
            "worst_low_mark_pct": round((low/entry-1)*100, 4),
            "broker_fill_verified": False,
        }
    return {
        "symbol": "ZPTA",
        "as_of": as_of,
        "original_signal_flags": snapshot["completed_day_signal_flags"],
        "original_research_candidate": snapshot["research_candidate"],
        "frozen_source_hash": snapshot["input_ohlcv_sha256"],
        "one_way_cost_assumption": one_way_cost,
        "future_outcomes": out,
        "fully_resolved": all(x is not None for x in out.values()),
        "independent_split_adjustment_verified": False,
        "real_money_trading_allowed": False,
        "warning": "Printed next-open and future close are NOT executable fills; no same-day-low entry.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot", type=Path)
    p.add_argument("daily_csv", type=Path)
    p.add_argument("--one-way-cost", type=float, default=.01)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    frozen = json.loads(args.snapshot.read_text(encoding="utf-8"))
    result = score_snapshot(frozen, load_daily(args.daily_csv), args.one_way_cost)
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as f:
            f.write(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
