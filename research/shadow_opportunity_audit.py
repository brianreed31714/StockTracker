#!/usr/bin/env python3
"""Read-only, evidence-backed StockTracker candidate and exit research.

Uses sanitized decisions and funnel CSVs, NOT a broker connection. A decision
price is an observation, not an executable fill. Backtests here are hypotheses,
not live/paper P/L. No settings, active processes, or orders are modified.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HORIZONS = (5, 15, 30, 60)
ONE_WAY_COST_BPS = 5.0
FIXED_STOP_PCT = 2.0
FIXED_TAKE_PCT = 3.0
TRAIL_ACTIVATE_PCT = 1.0
TRAIL_DISTANCE_PCT = 1.25


def timestamp(s):
    dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return dt


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as src:
        return list(csv.DictReader(src))


def pct(after, before):
    return (after / before - 1.0) * 100.0


def nearest_baseline(rows, event_time):
    if not rows:
        return None
    return min(rows, key=lambda r: abs((r["_ts"] - event_time).total_seconds()))


def forward_price(rows, start_time, minutes):
    target = start_time + timedelta(minutes=minutes)
    # Prefer the first observation at or after the horizon. Allow a 30-second
    # clock offset before, and at most a two-minute gap after the horizon.
    options = [r for r in rows if target - timedelta(seconds=30) <= r["_ts"]
               <= target + timedelta(minutes=2)]
    return min(options, key=lambda r: abs((r["_ts"] - target).total_seconds())) if options else None


def shadow_exit(rows, start_time, entry, *, trailing=False):
    """Counterfactual sampled-close exit, capped to 60 minutes within one session."""
    end = start_time + timedelta(minutes=60)
    future = [r for r in rows if start_time < r["_ts"] <= end]
    if not future or future[-1]["_ts"] < end - timedelta(minutes=2):
        return None  # No complete horizon: do not pretend a trade closed.
    peak = entry
    activated = False
    for r in future:
        price = r["_price"]
        peak = max(peak, price)
        if trailing and pct(peak, entry) >= TRAIL_ACTIVATE_PCT:
            activated = True
        if pct(price, entry) <= -FIXED_STOP_PCT:
            return {"exit": "FIXED_STOP", "gross_pct": round(pct(price, entry), 4)}
        if trailing and activated and pct(price, peak) <= -TRAIL_DISTANCE_PCT:
            return {"exit": "TRAILING_STOP", "gross_pct": round(pct(price, entry), 4)}
        if not trailing and pct(price, entry) >= FIXED_TAKE_PCT:
            return {"exit": "FIXED_TAKE", "gross_pct": round(pct(price, entry), 4)}
    return {"exit": "HORIZON_60M", "gross_pct": round(pct(future[-1]["_price"], entry), 4)}


def analyze(decisions, funnel, cost_bps=ONE_WAY_COST_BPS):
    by_symbol = defaultdict(list)
    for row in decisions:
        try:
            ts = timestamp(row["ts"])
            price = float(row["price"])
        except (ValueError, TypeError, KeyError):
            continue
        if price <= 0:
            continue
        by_symbol[row.get("symbol", "")].append({"_ts": ts, "_price": price, "score": row.get("score")})
    for rows in by_symbol.values():
        rows.sort(key=lambda r: r["_ts"])

    events = []
    last_episode = {}
    for gate in sorted(funnel, key=lambda r: r.get("ts", "")):
        if gate.get("side") not in {"BUY", "SELL"}:
            continue
        ts = timestamp(gate["ts"])
        symbol, side = gate.get("symbol", ""), gate["side"]
        rows = by_symbol[symbol]
        base = nearest_baseline(rows, ts)
        # Repeated one-minute logs are not independent trade opportunities.
        key = (symbol, side)
        if key not in last_episode or ts - last_episode[key][0] > timedelta(minutes=15):
            episode_id = len(events) + 1
            last_episode[key] = (ts, episode_id)
        else:
            episode_id = last_episode[key][1]
        result = {
            "symbol": symbol,
            "side": side,
            "timestamp": ts.isoformat(),
            "episode_id": episode_id,
            "gate": gate.get("gate_reason"),
            "position_state": gate.get("position_state"),
            "score": round(float(gate.get("score") or 0), 3),
            "entry_observation": None,
            "forward_gross_pct": {},
            "forward_after_cost_pct": {},
            "fixed_exit_60m": None,
            "trailing_exit_60m": None,
        }
        if base is not None and abs((base["_ts"] - ts).total_seconds()) <= 90:
            entry = base["_price"]
            result["entry_observation"] = entry
            for horizon in HORIZONS:
                later = forward_price(rows, ts, horizon)
                gross = round(pct(later["_price"], entry), 4) if later else None
                result["forward_gross_pct"][str(horizon)] = gross
                # Cost sensitivity only, not an actual spread/slippage measurement.
                result["forward_after_cost_pct"][str(horizon)] = (
                    round(gross - 2 * cost_bps / 100.0, 4) if gross is not None else None
                )
            if side == "BUY":
                for attr, trailing in (("fixed_exit_60m", False), ("trailing_exit_60m", True)):
                    outcome = shadow_exit(rows, ts, entry, trailing=trailing)
                    if outcome is not None:
                        outcome["after_cost_pct"] = round(outcome["gross_pct"] - 2 * cost_bps / 100.0, 4)
                    result[attr] = outcome
        events.append(result)
    missed = [e for e in events if e["side"] == "BUY" and
              e["gate"] != "ORDER_ACCEPTED" and e["position_state"] == "NO_POSITION"]
    sample_summary = {}
    for minutes in HORIZONS:
        cohort = [e["forward_after_cost_pct"][str(minutes)] for e in missed
                  if e["forward_after_cost_pct"].get(str(minutes)) is not None]
        sample_summary[str(minutes)] = {
            "event_observations": len(cohort),
            "positive_after_assumed_cost": sum(x > 0 for x in cohort),
            "average_after_assumed_cost_pct": round(sum(cohort) / len(cohort), 4) if cohort else None,
        }
    return {
        "mode": "SHADOW_RESEARCH_ONLY",
        "source": "sanitized decision observations and gate events",
        "one_way_cost_bps_assumed": cost_bps,
        "independence_warning": "Adjacent signals and horizons overlap; event observations are not independent samples.",
        "fill_warning": "1-minute observed prices omit intrabar stops, spread, market impact and broker fills.",
        "atr_status": "UNAVAILABLE_NO_OHLC_BARS",
        "portfolio_daily_return_pct": None,
        "portfolio_return_status": "UNVERIFIABLE_NO_START_END_EQUITY",
        "events": events,
        "missed_buy_forward_summary": sample_summary,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True,
                        help="Date-scoped evidence directory containing decisions.csv and decision_funnel.csv")
    parser.add_argument("--cost-bps", type=float, default=ONE_WAY_COST_BPS,
                        help="Assumed cost per side, basis points (default 5)")
    parser.add_argument("--output", type=Path, help="Optional local JSON output file")
    args = parser.parse_args()
    if not 0 <= args.cost_bps <= 100:
        parser.error("cost-bps must be between 0 and 100")
    result = analyze(read_csv(args.evidence / "decisions.csv"),
                     read_csv(args.evidence / "decision_funnel.csv"), args.cost_bps)
    data = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data + "\n", encoding="utf-8")
    else:
        print(data)


if __name__ == "__main__":
    main()
