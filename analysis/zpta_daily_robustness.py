"""Non-overlapping ZPTA HOLDOUT swing evaluation; research only, no broker access.

Every signal is known at completed day t. Hypothetical entry t+1 OPEN;
exit t+h CLOSE. No entry at the same-day low, no order-fill guarantee.
"""
from __future__ import annotations

import random
import statistics

from analysis.zpta_daily_swing_research import daily_signals, HORIZONS
from analysis.zpta_daily_validation import select_nonoverlapping, event_bootstrap_ci


COHORTS = (
    "one_day_decline_5pct",
    "two_down_days_total_5pct",
    "down_day_10pct_below_prior_ten_day_high",
    "rsi3_at_most_25",
    "confirmed_recovery_after_5pct_decline",
    "all_eligible_sessions",
)


def _summary(events):
    chosen = select_nonoverlapping(events)
    returns = [e["net_return_pct"] for e in chosen]
    ci = event_bootstrap_ci(returns)
    equity, peak, max_dd = 1.0, 1.0, 0.0
    for r in returns:
        equity *= 1+r/100
        peak = max(peak, equity)
        max_dd = min(max_dd, equity/peak-1)
    return {
        "overlapping_candidates": len(events),
        "independent_events": len(chosen),
        "mean_net_pct": ci["mean_pct"],
        "median_net_pct": ci.get("median_pct"),
        "bootstrap_mean_ci_pct": ci["ci_pct"],
        "bootstrap_warning": ci["warning"],
        "win_fraction": round(sum(r>0 for r in returns)/len(returns), 4) if returns else None,
        "mean_low_excursion_pct": round(statistics.mean(e["low_excursion_pct"] for e in chosen), 4) if chosen else None,
        "worst_trade_net_pct": round(min(returns), 4) if returns else None,
        "compounded_full_allocation_pct": round((equity-1)*100, 4) if chosen else None,
        "max_full_allocation_drawdown_pct": round(max_dd*100, 4) if chosen else None,
    }


def evaluate_holdout(bars, one_way_cost=0.01, min_signal_dollar_volume=25000, train_fraction=0.7):
    if not 0 <= one_way_cost < 0.5 or min_signal_dollar_volume < 0 or not 0 < train_fraction < 1:
        raise ValueError("Invalid parameters")
    cut = int(len(bars)*train_fraction)
    cohorts = {s: {h: [] for h in HORIZONS} for s in COHORTS}
    for i in range(max(10,cut),len(bars)-1):
        signal = bars[i]
        if signal["volume"] <= 0 or signal["close"]*signal["volume"] < min_signal_dollar_volume:
            continue
        flags = set(daily_signals(bars,i))
        for h in HORIZONS:
            if i+h >= len(bars):
                continue
            entry = bars[i+1]["open"]*(1+one_way_cost)
            exit_price = bars[i+h]["close"]*(1-one_way_cost)
            event = {
                "signal_index": i, "entry_index": i+1, "exit_index": i+h,
                "signal_date": signal["date"],
                "net_return_pct": (exit_price/entry-1)*100,
                "low_excursion_pct": (min(x["low"] for x in bars[i+1:i+h+1])/entry-1)*100,
            }
            for label in flags | {"all_eligible_sessions"}:
                cohorts[label][h].append(event)
    return {
        "total_sessions": len(bars),
        "train_sessions": cut,
        "holdout_sessions": len(bars)-cut,
        "holdout_start": bars[cut]["date"] if len(bars)>cut else None,
        "cost_one_way_pct": one_way_cost*100,
        "results": {s: {f"{h}d": _summary(cohorts[s][h]) for h in HORIZONS} for s in COHORTS},
        "limits": [
            "Data source and corporate-action adjustments still require independent verification.",
            "Chronological holdout was not guaranteed untouched before this study; descriptive evaluation only.",
            "Earliest-signal-first non-overlap is a deterministic research selection, not an optimized strategy.",
            "iid event bootstrap understates uncertainty when regimes are dependent or event count is small.",
            "Compounded full-allocation results ignore idle-cash yield, funding constraints and broker fill failures.",
            "One-percent each-side cost is a scenario, not measured OTC spreads.",
            "No same-day-low entry or assumed limit-order fill.",
        ],
    }
