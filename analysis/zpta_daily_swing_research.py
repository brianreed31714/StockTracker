"""Offline daily swing research for ZPTA. No broker access or trading changes.

Signals use only completed daily bars through t. Hypothetical entry is the
OPEN of session t+1 (never day-t's close or low). Exit is a later close.
Read-only cost sensitivity: OTC opening fills and bid/ask aren't verified.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from analysis.zpta_intraday_recovery import load_daily, chronological_gate

HORIZONS = (1, 3, 5)


def _mean(xs):
    return round(statistics.mean(xs), 4) if xs else None


def _median(xs):
    return round(statistics.median(xs), 4) if xs else None


def _rsi(closes, period=3):
    if len(closes) <= period:
        return None
    changes = [closes[i] - closes[i-1] for i in range(len(closes)-period, len(closes))]
    gain = sum(max(x, 0.0) for x in changes) / period
    loss = sum(max(-x, 0.0) for x in changes) / period
    if loss == 0:
        return 100.0 if gain else 50.0
    return 100 - 100 / (1 + gain / loss)


def daily_signals(bars, i):
    """Fixed hypotheses; all inputs were known at signal-day close."""
    if i < 10:
        return []
    today, prev, before = bars[i], bars[i-1], bars[i-2]
    close = today["close"]
    r1 = close / prev["close"] - 1
    prior_r1 = prev["close"] / before["close"] - 1
    rsi3 = _rsi([b["close"] for b in bars[:i+1]])
    prior_ten_high = max(b["high"] for b in bars[i-10:i])
    range_pos = ((close-today["low"]) / (today["high"]-today["low"])
                 if today["high"] > today["low"] else 0.5)
    flags = []
    if r1 <= -0.05:
        flags.append("one_day_decline_5pct")
    if r1 < 0 and prior_r1 < 0 and close / before["close"] - 1 <= -0.05:
        flags.append("two_down_days_total_5pct")
    if r1 < 0 and close <= 0.90 * prior_ten_high:
        flags.append("down_day_10pct_below_prior_ten_day_high")
    if rsi3 is not None and rsi3 <= 25:
        flags.append("rsi3_at_most_25")
    if prior_r1 <= -0.05 and r1 > 0 and range_pos >= 0.65:
        flags.append("confirmed_recovery_after_5pct_decline")
    return flags


def summarize_events(events):
    if not events:
        return {"events": 0, "mean_net_return_pct": None,
                "median_net_return_pct": None, "win_fraction": None,
                "mean_worst_excursion_pct": None}
    ret = [e["net_return_pct"] for e in events]
    return {"events": len(events), "mean_net_return_pct": _mean(ret),
            "median_net_return_pct": _median(ret),
            "win_fraction": round(sum(x > 0 for x in ret)/len(ret), 4),
            "mean_worst_excursion_pct": _mean([e["worst_excursion_pct"] for e in events])}


def research(bars, one_way_cost=0.01, min_signal_dollar_volume=25000,
             min_train_sessions=100, min_test_sessions=30):
    if not 0 <= one_way_cost < 0.5 or min_signal_dollar_volume < 0:
        raise ValueError("Invalid cost / volume floor")
    gate = chronological_gate(bars, min_train=min_train_sessions, min_test=min_test_sessions)
    cut = int(len(bars) * .7)
    signal_names = ("one_day_decline_5pct", "two_down_days_total_5pct",
                    "down_day_10pct_below_prior_ten_day_high", "rsi3_at_most_25",
                    "confirmed_recovery_after_5pct_decline", "all_eligible_sessions")
    cohorts = {name: {h: {"training": [], "holdout": [], "all": []} for h in HORIZONS}
               for name in signal_names}
    volume_filtered = 0
    for i in range(10, len(bars)-1):
        signal = bars[i]
        if signal["volume"] <= 0 or signal["close"] * signal["volume"] < min_signal_dollar_volume:
            volume_filtered += 1
            continue
        labels = daily_signals(bars, i) + ["all_eligible_sessions"]
        for h in HORIZONS:
            exit_idx = i + h
            if exit_idx >= len(bars):
                continue
            buy_px = bars[i+1]["open"] * (1 + one_way_cost)
            sell_px = bars[exit_idx]["close"] * (1 - one_way_cost)
            ev = {
                "signal_date": signal["date"], "entry_date": bars[i+1]["date"],
                "exit_date": bars[exit_idx]["date"], "signal_index": i,
                "exit_index": exit_idx,
                "net_return_pct": round((sell_px/buy_px - 1) * 100, 4),
                "worst_excursion_pct": round(
                    (min(b["low"] for b in bars[i+1:exit_idx+1])/buy_px - 1)*100, 4)
            }
            for name in labels:
                cohorts[name][h]["all"].append(ev)
                if exit_idx < cut:
                    cohorts[name][h]["training"].append(ev)
                elif i >= cut:
                    cohorts[name][h]["holdout"].append(ev)
                # Purge training outcomes that overlap the holdout.
    report = {
        "sessions": len(bars),
        "first_date": bars[0]["date"] if bars else None,
        "last_date": bars[-1]["date"] if bars else None,
        "one_way_cost_assumption": one_way_cost,
        "min_signal_dollar_volume": min_signal_dollar_volume,
        "volume_filtered_signal_days": volume_filtered,
        "validation_gate": gate,
        "signal_results": {name: {f"{h}d": {k: summarize_events(v) for k, v in splits.items()}
                                  for h, splits in horizons.items()}
                           for name, horizons in cohorts.items()},
        "limitations": [
            "Fixed descriptive hypotheses, not demonstrated predictive skill or a trading recommendation.",
            "One-percent each-side costs are hypothetical; actual OTC quote spreads may be worse.",
            "Next-open printed price is not necessarily an executable broker fill.",
            "No same-day low entry assumed; signals actionable from the next session.",
            "Overlapping horizons and cohorts are not independent trades.",
            "Daily OHLC cannot establish ordering of intraday low and high or stop execution.",
            "Training events whose exit falls in holdout are embargoed.",
            "Historical OHLCV must have verified split adjustments, source and positive volume.",
            "No sequential portfolio returns/drawdown or statistical significance computed.",
        ],
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("daily_csv", type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--split-adjustment-verified", action="store_true")
    parser.add_argument("--one-way-cost", type=float, default=0.01)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = research(load_daily(args.daily_csv), one_way_cost=args.one_way_cost)
    report["source"] = args.source
    report["split_adjustment_verified"] = args.split_adjustment_verified
    report["eligible_for_model_selection"] = bool(
        args.split_adjustment_verified and
        report["validation_gate"]["status"] == "READY_FOR_TRAIN_ONLY_SELECTION")
    report["eligible_for_live_trading"] = False
    txt = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(txt, encoding="utf-8")
    else:
        print(txt, end="")


if __name__ == "__main__":
    main()
