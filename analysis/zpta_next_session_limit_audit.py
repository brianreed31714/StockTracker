"""Read-only next-session ZPTA dip-limit counterfactuals.

Only signal-day completed OHLCV sets a limit; future daily lows never prove
an executable fill. Open-at-or-below-limit prints are explicitly hypothetical.
No broker connectivity, no risk-setting changes, no order placement.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.zpta_daily_swing_research import daily_signals, HORIZONS
from analysis.zpta_intraday_recovery import load_daily


def limit_price(bars, i, discount=.03, lookback=5):
    """Precommitted price using ONLY completed bars up to signal day i."""
    if i < lookback - 1 or not 0 <= discount < 1:
        raise ValueError("Invalid lookback or discount")
    if any(b["low"] <= 0 or b["close"] <= 0 for b in bars[i-lookback+1:i+1]):
        raise ValueError("Invalid historical prices")
    return min(bars[i]["close"] * (1 - discount),
               min(b["low"] for b in bars[i-lookback+1:i+1]))


def classify_next_session(limit, next_bar):
    """An intraday touch alone is NOT evidence of a fill."""
    if next_bar is None:
        return "PENDING_NEXT_SESSION"
    if next_bar["open"] <= limit:
        return "OPEN_PRINT_ELIGIBLE_UNVERIFIED"
    if next_bar["low"] <= limit:
        return "INTRADAY_TOUCH_NO_FILL_ASSUMED"
    return "LIMIT_NOT_REACHED"


def audit(bars, signal_name="one_day_decline_5pct", discount=.03,
          one_way_cost=.01, min_signal_dollar_volume=25000):
    if not 0 <= one_way_cost < .5 or not 0 <= discount < 1 or min_signal_dollar_volume < 0:
        raise ValueError("Invalid cost, discount or turnover threshold")
    dates = [b["date"] for b in bars]
    if dates != sorted(set(dates)):
        raise ValueError("Daily bars must be strictly chronological")
    if signal_name not in (
        "one_day_decline_5pct", "two_down_days_total_5pct",
        "down_day_10pct_below_prior_ten_day_high", "rsi3_at_most_25",
        "confirmed_recovery_after_5pct_decline"):
        raise ValueError("Unknown preregistered signal")
    cut = int(len(bars) * .7)
    candidates = []
    for i in range(10, len(bars)):
        b = bars[i]
        if b["volume"] <= 0 or b["close"] * b["volume"] < min_signal_dollar_volume:
            continue
        if signal_name not in daily_signals(bars, i):
            continue
        limit = limit_price(bars, i, discount)
        nxt = bars[i+1] if i+1 < len(bars) else None
        candidates.append({
            "signal_date": b["date"], "signal_index": i,
            "limit_price": round(limit, 8),
            "next_session_date": nxt["date"] if nxt else None,
            "status": classify_next_session(limit, nxt),
            "broker_fill_verified": False,
            "horizon_outcomes": {},
        })
        for h in HORIZONS:
            outcome = None
            if nxt is not None and i+h < len(bars) and nxt["open"] <= limit:
                entry_cost = limit * (1 + one_way_cost)
                exit_net = bars[i+h]["close"] * (1 - one_way_cost)
                baseline_cost = nxt["open"] * (1 + one_way_cost)
                outcome = {
                    "exit_date": bars[i+h]["date"],
                    "limit_open_print_scenario_net_pct": round(100*(exit_net/entry_cost-1), 4),
                    "same_signal_next_open_baseline_net_pct": round(100*(exit_net/baseline_cost-1), 4),
                    "worst_low_mark_pct": round(100*(
                        min(x["low"] for x in bars[i+1:i+h+1])/entry_cost-1), 4),
                    "broker_fill_verified": False,
                    "sample": ("training" if i+h < cut else
                               "already_examined_holdout" if i >= cut else "embargo"),
                }
            candidates[-1]["horizon_outcomes"][f"{h}d"] = outcome
    counts = {status: sum(c["status"] == status for c in candidates)
              for status in ("OPEN_PRINT_ELIGIBLE_UNVERIFIED",
                             "INTRADAY_TOUCH_NO_FILL_ASSUMED",
                             "LIMIT_NOT_REACHED", "PENDING_NEXT_SESSION")}
    independent = {}
    for h in HORIZONS:
        last_exit = -1
        selected = []
        for c in candidates:
            i = c["signal_index"]
            event = c["horizon_outcomes"][f"{h}d"]
            if event is None or i <= last_exit:
                continue
            selected.append(event)
            last_exit = i+h
        independent[f"{h}d"] = {
            "nonoverlapping_open_print_scenarios": len(selected),
            "training": sum(e["sample"] == "training" for e in selected),
            "already_examined_holdout": sum(e["sample"] == "already_examined_holdout" for e in selected),
            "embargo": sum(e["sample"] == "embargo" for e in selected),
            "mean_net_pct": round(sum(e["limit_open_print_scenario_net_pct"] for e in selected)/len(selected), 4) if selected else None,
            "mean_same_date_next_open_baseline_pct": round(sum(e["same_signal_next_open_baseline_net_pct"] for e in selected)/len(selected), 4) if selected else None,
        }
    return {
        "symbol": "ZPTA", "signal_name": signal_name, "limit_discount": discount,
        "one_way_cost_assumption": one_way_cost,
        "min_signal_dollar_volume": min_signal_dollar_volume,
        "candidate_count": len(candidates), "limit_status_counts": counts,
        "nonoverlapping_summary": independent, "candidates": candidates,
        "data_adjustment_verified": False, "executable_quotes_verified": False,
        "real_money_trading_allowed": False,
        "limitations": [
            "No intraday low/touch is counted as an executed order.",
            "Open-at-or-below-limit is a hypothetical printed-price scenario, NOT a verified fill.",
            "The limit uses completed signal-day data only; entry cannot occur until next session.",
            "A limit touched after the open is marked unfilled without quote/trade sequencing.",
            "Already examined historical holdout cannot establish new out-of-sample skill.",
            "No independently verified adjusted history, bid/ask size, queue position or fill costs.",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("daily_csv", type=Path)
    p.add_argument("--source", required=True)
    p.add_argument("--signal", default="one_day_decline_5pct")
    p.add_argument("--discount", type=float, default=.03)
    p.add_argument("--one-way-cost", type=float, default=.01)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    report = audit(load_daily(args.daily_csv), signal_name=args.signal,
                   discount=args.discount, one_way_cost=args.one_way_cost)
    report["source"] = args.source
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as out:
            out.write(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
