"""Non-overlapping ZPTA HOLDOUT swing evaluation; research only, no broker access.

Every signal is known at completed day t. Hypothetical entry t+1 OPEN;
exit t+h CLOSE. No entry at the same-day low, no order-fill guarantee.
"""
from __future__ import annotations

import math
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
    gross_wins = sum(max(0, r) for r in returns)
    gross_losses = -sum(min(0, r) for r in returns)
    profit_factor = (gross_wins / gross_losses if gross_losses > 0 else None)
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
        "gross_profit_to_loss_ratio": round(profit_factor, 4) if profit_factor is not None else None,
        "mean_low_excursion_pct": round(statistics.mean(e["low_excursion_pct"] for e in chosen), 4) if chosen else None,
        "worst_trade_net_pct": round(min(returns), 4) if returns else None,
        "compounded_full_allocation_pct": round((equity-1)*100, 4) if chosen else None,
        "max_full_allocation_drawdown_pct": round(max_dd*100, 4) if chosen else None,
    }



def _matched_month_liquidity_excess(signal_events, eligible_events, horizon):
    """Observational same-month, similar-turnover controls, never matched on returns.

    Exclude same signal dates and +/- horizon days to reduce shared price paths.
    Matched controls may still overlap each other; CI is descriptive, not causal.
    """
    independent = select_nonoverlapping(signal_events)
    signal_indices = {e["signal_index"] for e in signal_events}
    excess = []
    for e in independent:
        pool = [
            c for c in eligible_events
            if c["month"] == e["month"]
            and c["signal_index"] not in signal_indices
            and abs(c["signal_index"] - e["signal_index"]) > horizon
        ]
        if not pool:
            continue
        # Use only features available by each control's completed signal day.
        control = min(pool, key=lambda c: (
            abs(math.log(c["turnover"] / e["turnover"])) +
            abs(c["range_fraction"] - e["range_fraction"]),
            abs(c["signal_index"] - e["signal_index"]),
        ))
        excess.append(e["net_return_pct"] - control["net_return_pct"])
    ci = event_bootstrap_ci(excess)
    return {
        "matched_pairs": len(excess),
        "mean_excess_net_pct": ci["mean_pct"],
        "median_excess_net_pct": ci.get("median_pct"),
        "bootstrap_excess_ci_pct": ci["ci_pct"],
        "warning": "OBSERVATIONAL_MATCHES_NOT_INDEPENDENT_OR_CAUSAL",
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
                "signal_date": signal["date"], "month": signal["date"][:7],
                "turnover": signal["close"] * signal["volume"],
                "range_fraction": (signal["high"]-signal["low"])/signal["close"],
                "net_return_pct": (exit_price/entry-1)*100,
                "low_excursion_pct": (min(x["low"] for x in bars[i+1:i+h+1])/entry-1)*100,
            }
            for label in flags | {"all_eligible_sessions"}:
                cohorts[label][h].append(event)
    summaries = {s: {f"{h}d": _summary(cohorts[s][h]) for h in HORIZONS} for s in COHORTS}
    for s in COHORTS:
        if s == "all_eligible_sessions":
            continue
        for h in HORIZONS:
            summaries[s][f"{h}d"]["matched_month_liquidity"] = (
                _matched_month_liquidity_excess(cohorts[s][h], cohorts["all_eligible_sessions"][h], h)
            )
    return {
        "total_sessions": len(bars),
        "train_sessions": cut,
        "holdout_sessions": len(bars)-cut,
        "holdout_start": bars[cut]["date"] if len(bars)>cut else None,
        "cost_one_way_pct": one_way_cost*100,
        "results": summaries,
        "limits": [
            "Data source and corporate-action adjustments still require independent verification.",
            "Chronological holdout was not guaranteed untouched before this study; descriptive evaluation only.",
            "Earliest-signal-first non-overlap is a deterministic research selection, not an optimized strategy.",
            "iid event bootstrap understates uncertainty when regimes are dependent or event count is small.",
            "Compounded full-allocation results ignore idle-cash yield, funding constraints and broker fill failures.",
            "One-percent each-side cost is a scenario, not measured OTC spreads.",
            "No same-day-low entry or assumed limit-order fill.",
            "Same-month turnover-matched controls are observational, may overlap and do not establish causality.",
        ],
    }
