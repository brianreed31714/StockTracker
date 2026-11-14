"""Read-only ZPTA historical venue-regime audit.

The 501-session price history crosses changes in issuer trading access:
Dec 15 2025 issuer reports move from OTC Expert to Pink Limited;
Jun 16 2026 issuer reports OTCQB quotation effective for trading.
Do not pool those sessions to infer present-day OTCQB execution quality.
Pre-Dec 2025 is labelled LEGACY_UNVERIFIED because it also includes an
earlier Nasdaq period, not exclusively Expert Market.

All signals use completed day t, enter no earlier than day t+1 OPEN,
and exit at day t+h CLOSE. No real fills, broker calls, or live orders.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

from analysis.zpta_daily_swing_research import daily_signals
from analysis.zpta_daily_validation import select_nonoverlapping, event_bootstrap_ci
from analysis.zpta_intraday_recovery import load_daily

TRANSITION_TO_POST_EXPERT = "2025-12-15"
OTCQB_EFFECTIVE = "2026-06-16"
REGIMES = ("LEGACY_PRE_DEC_2025_UNVERIFIED", "POST_EXPERT_PRE_OTCQB",
           "OTCQB_FROM_2026_06_16")
SIGNALS = ("one_day_decline_5pct", "two_down_days_total_5pct",
           "down_day_10pct_below_prior_ten_day_high", "rsi3_at_most_25",
           "confirmed_recovery_after_5pct_decline", "all_eligible_sessions")
HORIZONS = (1, 3, 5)


def venue_regime(day):
    if day < TRANSITION_TO_POST_EXPERT:
        return REGIMES[0]
    if day < OTCQB_EFFECTIVE:
        return REGIMES[1]
    return REGIMES[2]


def _metrics(events):
    chosen = select_nonoverlapping(events)
    returns = [x["net_pct"] for x in chosen]
    if not returns:
        return {"candidates": len(events), "independent_trades": 0,
                "mean_net_pct": None, "median_net_pct": None,
                "bootstrap_ci_pct": None, "profit_factor": None,
                "max_compounded_drawdown_pct": None}
    ci = event_bootstrap_ci(returns, resamples=2000)
    wins = sum(max(0.0, r) for r in returns)
    losses = -sum(min(0.0, r) for r in returns)
    equity, peak, dd = 1.0, 1.0, 0.0
    for r in returns:
        equity *= 1 + r / 100
        peak = max(peak, equity)
        dd = min(dd, equity / peak - 1)
    return {"candidates": len(events), "independent_trades": len(chosen),
            "mean_net_pct": ci["mean_pct"],
            "median_net_pct": ci["median_pct"],
            "bootstrap_ci_pct": ci["ci_pct"],
            "profit_factor": round(wins / losses, 4) if losses > 0 else None,
            "max_compounded_drawdown_pct": round(100 * dd, 4)}


def audit_regimes(bars, as_of="2026-10-23", one_way_cost=0.01,
                  min_signal_dollar_volume=25000):
    if not 0 <= one_way_cost < 0.5 or min_signal_dollar_volume < 0:
        raise ValueError("Invalid cost or liquidity floor")
    bars = [b for b in bars if b["date"] <= as_of]
    if not bars:
        raise ValueError("No bars on or before cutoff")
    if any(bars[i]["date"] >= bars[i + 1]["date"] for i in range(len(bars) - 1)):
        raise ValueError("Daily bars must be strictly ordered")
    if any(min(b["open"], b["high"], b["low"], b["close"]) <= 0 or
           b["volume"] < 0 for b in bars):
        raise ValueError("Invalid OHLCV")
    counters = {r: {"sessions": 0, "positive_volume_sessions": 0,
                    "signal_day_liquid_sessions": 0, "zero_volume_sessions": 0,
                    "dollar_turnovers": []} for r in REGIMES}
    cohorts = {r: {name: {h: [] for h in HORIZONS} for name in SIGNALS}
               for r in REGIMES}
    for b in bars:
        c = counters[venue_regime(b["date"])]
        c["sessions"] += 1
        turnover = b["close"] * b["volume"]
        c["dollar_turnovers"].append(turnover)
        c["positive_volume_sessions"] += int(b["volume"] > 0)
        c["zero_volume_sessions"] += int(b["volume"] == 0)
        c["signal_day_liquid_sessions"] += int(
            b["volume"] > 0 and turnover >= min_signal_dollar_volume)
    boundary_crossings = Counter()
    for i in range(10, len(bars) - 1):
        b = bars[i]
        reg = venue_regime(b["date"])
        if b["volume"] <= 0 or b["close"] * b["volume"] < min_signal_dollar_volume:
            continue
        labels = set(daily_signals(bars, i)) | {"all_eligible_sessions"}
        for h in HORIZONS:
            exit_i = i + h
            if exit_i >= len(bars):
                continue
            if any(venue_regime(bars[j]["date"]) != reg
                   for j in range(i + 1, exit_i + 1)):
                boundary_crossings[f"{h}d"] += 1
                continue
            entry = bars[i + 1]["open"] * (1 + one_way_cost)
            exit_px = bars[exit_i]["close"] * (1 - one_way_cost)
            event = {"entry_index": i + 1, "exit_index": exit_i,
                     "net_pct": 100 * (exit_px / entry - 1)}
            for name in labels:
                cohorts[reg][name][h].append(event)
    summary = {}
    for reg in REGIMES:
        c = counters[reg]
        turns = c.pop("dollar_turnovers")
        c["median_daily_dollar_turnover"] = (
            round(statistics.median(turns), 2) if turns else None)
        c["signal_day_liquid_fraction"] = (
            round(c["signal_day_liquid_sessions"] / c["sessions"], 4)
            if c["sessions"] else None)
        summary[reg] = {"liquidity": c,
                        "strategies": {
                            name: {f"{h}d": _metrics(cohorts[reg][name][h])
                                   for h in HORIZONS}
                            for name in SIGNALS}}
    latest = bars[-1]
    last_reg = venue_regime(latest["date"])
    last_flags = daily_signals(bars, len(bars) - 1)
    last_turnover = latest["close"] * latest["volume"]
    return {
        "cutoff": as_of, "last_date": latest["date"], "last_close": latest["close"],
        "last_volume": latest["volume"], "last_venue_regime": last_reg,
        "last_signal_flags": last_flags,
        "last_signal_day_liquid": latest["volume"] > 0 and
            last_turnover >= min_signal_dollar_volume,
        "last_dollar_turnover": round(last_turnover, 2),
        "sessions_analyzed": len(bars),
        "one_way_cost": one_way_cost,
        "min_signal_dollar_volume": min_signal_dollar_volume,
        "cross_venue_events_excluded": dict(boundary_crossings),
        "regimes": summary,
        "promotion_allowed": False,
        "warnings": [
            "PRE_DEC_2025_HISTORY_MIXES_NASDAQ_AND_OTC_EXPERT_NO_EXECUTION_COMPARABILITY",
            "DEC_2025_TO_JUN_2026_VENUE_HISTORY_NOT_INDEPENDENTLY_VERIFIED",
            "OTCQB_ONLY_SAMPLE_IS_SHORT_AND_HOLDOUT_ALREADY_EXAMINED",
            "SPLIT_ADJUSTMENT_AND_BROKER_FILL_QUALITY_NOT_VERIFIED",
            "BOOTSTRAP_IS_IID_AND_SMALL_SAMPLE_NOT_A_PREDICTIVE_PROOF",
            "PRINTED_NEXT_OPEN_AND_EXIT_CLOSE_NOT_GUARANTEED_FILLS",
            "HISTORICAL_MARKET_DATA_DISTRIBUTION_RIGHTS_NOT_VERIFIED",
        ],
        "primary_sources": [
            "https://investors.zapataquantum.com/news-releases/news-release-details/zapata-quantum-now-current-sec-reporting-enabling-broader",
            "https://investors.zapataquantum.com/node/8026/pdf",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("daily_csv", type=Path)
    parser.add_argument("--as-of", default="2026-10-23")
    parser.add_argument("--one-way-cost", type=float, default=.01)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_regimes(load_daily(args.daily_csv), as_of=args.as_of,
                           one_way_cost=args.one_way_cost)
    out = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out, end="")


if __name__ == "__main__":
    main()
