"""Read-only ZPTA intraday dip research from daily split-consistent OHLCV.

No market orders, network access, or modifications to the existing ZPTA sleeve.
Signals use only the previous close and the signal day's completed OHLCV.
The next-session open-to-close simulation is a cost-sensitivity experiment, not
an executable fill model; daily bars contain no spread, depth or intraday order.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from datetime import date
from pathlib import Path


def load_daily(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        records = list(csv.DictReader(stream))
    bars = []
    for raw in records:
        row = {str(k).strip().lower(): v for k, v in raw.items() if k}
        day = date.fromisoformat(row["date"][:10]).isoformat()
        bar = {"date": day}
        for key in ("open", "high", "low", "close", "volume"):
            bar[key] = float(row[key])
        if not all(math.isfinite(bar[k]) for k in ("open", "high", "low", "close", "volume")):
            raise ValueError(f"Nonfinite OHLCV: {day}")
        if min(bar[k] for k in ("open", "high", "low", "close")) <= 0 or bar["volume"] < 0:
            raise ValueError(f"Invalid price or volume: {day}")
        if bar["high"] < max(bar["open"], bar["close"], bar["low"]) or bar["low"] > min(bar["open"], bar["close"]):
            raise ValueError(f"Inconsistent OHLC: {day}")
        bars.append(bar)
    bars.sort(key=lambda b: b["date"])
    if len({b["date"] for b in bars}) != len(bars):
        raise ValueError("Duplicate trading dates")
    return bars


def avg(values):
    return round(statistics.mean(values), 6) if values else None


def summarize(bars: list[dict], thresholds=(0.05, 0.10, 0.15),
              one_way_costs=(0.01, 0.03, 0.05),
              position_dollars=150.0, max_prior_day_volume_fraction=0.01,
              min_prior_day_dollar_volume=25000.0, min_notional=25.0) -> dict:
    """Compute intraday recovery descriptives and next-day cost sensitivity.

    Uses the signal day's completed volume as a liquidity proxy. No use of next
    day's volume to decide trade sizing. No stop/take-profit assumptions.
    """
    if position_dollars <= 0 or not 0 < max_prior_day_volume_fraction <= 1 or min_notional <= 0:
        raise ValueError("Invalid position/liquidity configuration")
    if any(not 0 <= c < 0.5 for c in one_way_costs):
        raise ValueError("Invalid one-way cost")
    result = {"sessions": len(bars), "first_date": bars[0]["date"] if bars else None,
              "last_date": bars[-1]["date"] if bars else None, "thresholds": {}}
    for threshold in thresholds:
        if not 0 < threshold < 1:
            raise ValueError("Invalid dip threshold")
        events = []
        for i in range(1, len(bars)):
            prior, signal = bars[i - 1], bars[i]
            drawdown = signal["low"] / prior["close"] - 1
            if drawdown > -threshold:
                continue
            loss = prior["close"] - signal["low"]
            recovery = (signal["close"] - signal["low"]) / loss if loss > 0 else None
            event = {"date": signal["date"],
                     "prior_close_to_low_pct": round(drawdown * 100, 4),
                     "low_to_close_pct": round((signal["close"] / signal["low"] - 1) * 100, 4),
                     "half_recovered_at_close": recovery is not None and recovery >= 0.5,
                     "fully_recovered_at_close": recovery is not None and recovery >= 1.0,
                     "signal_day_dollar_volume": round(signal["close"] * signal["volume"], 2),
                     "next_day_available": i + 1 < len(bars)}
            if i + 1 < len(bars):
                following = bars[i + 1]
                event["next_open_to_close_gross_pct"] = round((following["close"] / following["open"] - 1) * 100, 4)
                event["next_open_gap_pct"] = round((following["open"] / signal["close"] - 1) * 100, 4)
                # A conservative proxy using only *known signal-day* turnover.
                # The real order book may support much less size.
                cap = min(position_dollars, signal["close"] * signal["volume"] * max_prior_day_volume_fraction)
                event["hypothetical_notional_cap"] = round(cap, 2)
                event["liquidity_proxy_pass"] = (signal["close"] * signal["volume"] >= min_prior_day_dollar_volume and cap >= min_notional)
                for cost in one_way_costs:
                    key = f"next_day_net_{int(round(cost * 100))}pct_each_side_pct"
                    event[key] = round(((following["close"] * (1 - cost)) / (following["open"] * (1 + cost)) - 1) * 100, 4) if event["liquidity_proxy_pass"] else None
            events.append(event)
        eligible = [e for e in events if e["next_day_available"]]
        tradeable = [e for e in eligible if e.get("liquidity_proxy_pass")]
        summary = {"events": len(events), "next_day_observable": len(eligible),
                   "half_recovered_by_same_close": sum(e["half_recovered_at_close"] for e in events),
                   "fully_recovered_by_same_close": sum(e["fully_recovered_at_close"] for e in events),
                   "median_low_to_close_pct": round(statistics.median(e["low_to_close_pct"] for e in events), 4) if events else None,
                   "liquidity_proxy_eligible": len(tradeable),
                   "next_day_open_to_close_mean_gross_pct": avg([e["next_open_to_close_gross_pct"] for e in eligible])}
        for cost in one_way_costs:
            key = f"next_day_net_{int(round(cost * 100))}pct_each_side_pct"
            returns = [e[key] for e in tradeable]
            summary[key] = {"observations": len(returns), "mean_pct": avg(returns),
                            "positive_fraction": round(sum(v > 0 for v in returns) / len(returns), 4) if returns else None}
        result["thresholds"][f"{threshold:.0%}"] = {"summary": summary, "events": events}
    result["limitations"] = [
        "Low-to-close is descriptive and cannot assume entry at the daily low.",
        "The same-day low may occur before or after the high; daily bars omit ordering.",
        "Next-day open-to-close is hypothetical; OTC opening fills and liquidity are unverified.",
        "Costs are symmetric scenario assumptions, not observed bid/ask spreads.",
        "Prior-day dollar volume is only a liquidity proxy; no order-book evidence.",
        "Events may overlap across thresholds and are not independent.",
        "Input prices and volumes must be split-consistent and sourced from licensed/verified history.",
    ]
    return result


def chronological_gate(bars: list[dict], train_fraction=0.7, min_train=100, min_test=30):
    """Require a meaningful untouched test period before model selection."""
    cut = int(len(bars) * train_fraction)
    if cut < min_train or len(bars) - cut < min_test:
        return {"status": "INSUFFICIENT_HISTORY", "train_sessions": cut,
                "test_sessions": len(bars) - cut, "min_train": min_train, "min_test": min_test}
    return {"status": "READY_FOR_TRAIN_ONLY_SELECTION", "train_sessions": cut,
            "test_sessions": len(bars) - cut, "train_end": bars[cut - 1]["date"],
            "test_start": bars[cut]["date"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv_path", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--source", required=True, help="Provider/source of split-consistent daily OHLCV")
    p.add_argument("--split-adjustment-verified", action="store_true", help="Explicitly confirm corporate-action adjustments")
    args = p.parse_args()
    bars = load_daily(args.csv_path)
    report = summarize(bars)
    report["source"] = args.source
    report["split_adjustment_verified"] = args.split_adjustment_verified
    report["validation_gate"] = chronological_gate(bars)
    report["eligible_for_model_selection_research"] = bool(args.split_adjustment_verified and report["validation_gate"]["status"] == "READY_FOR_TRAIN_ONLY_SELECTION")
    report["eligible_for_strategy_promotion"] = False
    serialized = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
