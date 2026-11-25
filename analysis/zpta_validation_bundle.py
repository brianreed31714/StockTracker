"""Reproducible offline completion of the five ZPTA research PRs.

Private source CSV/SQLite inputs; no broker/trader imports, network or orders.
Outputs separate descriptive scenarios, source gaps and actual paper activity.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import date
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import statistics

from analysis.zpta_daily_swing_research import daily_signals, HORIZONS
from analysis.zpta_independent_holdout import select_nonoverlapping, evaluate
from analysis.zpta_intraday_recovery import load_daily
from analysis.zpta_entry_volume_validation import evaluate as volume_events, summarize, bootstrap_rate_diff
from research.zpta_opportunity_audit import dip_score, liquidity_counterfactual


def volatility(bars, i):
    returns = [bars[j]["close"] / bars[j-1]["close"] - 1 for j in range(i-19, i+1)]
    return statistics.pstdev(returns)


def week_interval(events, iterations=1000):
    blocks = {}
    for e in events:
        iso = date.fromisoformat(e["signal_date"]).isocalendar()
        blocks.setdefault((iso.year, iso.week), []).append(e["net_return_pct"])
    if len(blocks) < 5:
        return None
    rng = random.Random(20261125)
    values = list(blocks.values())
    samples = sorted(statistics.mean(x for _ in values for x in rng.choice(values)) for _ in range(iterations))
    return {"ci95_pct": [samples[int(.025 * iterations)], samples[int(.975 * iterations)]],
            "weeks": len(values), "method": "week-cluster exploratory bootstrap"}


def independent_daily(bars, cost=.01):
    if not 0 <= cost < .5:
        raise ValueError("Invalid hypothetical friction")
    cutoff = int(len(bars) * .7)
    results = {}
    for horizon in HORIZONS:
        universe = []
        for i in range(20, len(bars)-horizon):
            b, entry, exit_ = bars[i], bars[i+1], bars[i+horizon]
            if b["close"] * b["volume"] < 25000:
                continue
            universe.append({"signal_index": i, "exit_index": i+horizon,
                             "signal_date": b["date"], "weekday": date.fromisoformat(b["date"]).weekday(),
                             "volatility": volatility(bars, i), "flags": daily_signals(bars, i),
                             "net_return_pct": 100 * (exit_["close"] * (1-cost) / (entry["open"] * (1+cost)) - 1),
                             "next_open_gap_pct": 100 * (entry["open"] / b["close"] - 1)})
        names = sorted({name for ev in universe for name in ev["flags"]})
        for name in names:
            for segment in ("training", "holdout"):
                pool = select_nonoverlapping(universe, split_index=cutoff, segment=segment, embargo_sessions=5)
                # Filter before selecting: another strategy cannot occupy this cohort's cash.
                signals = select_nonoverlapping([e for e in universe if name in e["flags"]],
                                                 split_index=cutoff, segment=segment, embargo_sessions=5)
                allowed = [e for e in universe if (e["exit_index"] < cutoff-5 if segment == "training"
                                                  else e["signal_index"] >= cutoff+5)]
                controls, failures = [], 0
                for ev in signals:
                    candidates = [e for e in allowed if e["weekday"] == ev["weekday"]
                                  and abs(e["signal_index"] - ev["signal_index"]) <= 30
                                  and not (e["signal_index"] <= ev["exit_index"] and ev["signal_index"] <= e["exit_index"])
                                  and all(not (e["signal_index"]+1 <= c["exit_index"]
                                               and c["signal_index"]+1 <= e["exit_index"]) for c in controls)]
                    if not candidates:
                        failures += 1
                        continue
                    controls.append(min(candidates, key=lambda e: (abs(e["volatility"]-ev["volatility"]), e["signal_index"])))
                results[f"{name}/{horizon}d/{segment}"] = {
                    "signals": evaluate(signals), "signal_week_interval": week_interval(signals),
                    "weekday_volatility_matched_controls": evaluate(controls),
                    "unmatched_signals": failures, "eligible_nonoverlap_baseline_count": len(pool),
                    "signal_dates": [e["signal_date"] for e in signals],
                    "scenario": "PRINTED_NEXT_OPEN_TO_LATER_CLOSE_WITH_ASSUMED_FRICTION"}
    return {"cutoff_index": cutoff, "embargo_sessions": 5, "one_way_cost": cost,
            "eligible_for_promotion": False, "results": results,
            "limitations": ["Exploratory historical splits have been examined; not pristine holdout.",
                            "Source adjustments and executable OTC quotes remain unverified.",
                            "Matching uses known signal-day features only; not a causal comparison.",
                            "Trade-sequence compounding is not sized portfolio ROI."]}


def legacy_replay(db_path, start="2026-10-21", end="2026-10-27"):
    """Audit preserved observations without inventing missing minute bars/fills."""
    date.fromisoformat(start)
    date.fromisoformat(end)
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("SELECT ts,provider,price,volume,features_json,regime FROM zpta_observations "
                          "WHERE substr(ts,1,10) BETWEEN ? AND ? ORDER BY ts", (start, end)).fetchall()
        forecasts = db.execute("SELECT bar_ts,model,score,created_ts,due_ts FROM zpta_predictions "
                               "WHERE substr(bar_ts,1,10) BETWEEN ? AND ? ORDER BY bar_ts,model", (start,end)).fetchall()
        trades = db.execute("SELECT COUNT(*) FROM zpta_shadow_trades WHERE substr(entry_ts,1,10) BETWEEN ? AND ?", (start,end)).fetchone()[0]
    records = []
    for ts, provider, price, volume, raw, regime in rows:
        f = json.loads(raw)
        models = {model: score for b,model,score,created,due in forecasts if b == ts}
        records.append({"bar_ts": ts, "provider": provider, "features": f, "regime": regime,
                        "original_model_scores": models, "dip_recovery_hunter": dip_score(f),
                        "receipt_timestamp_verified": False, "verified_fill": False})
    by_day = Counter(r[0][:10] for r in rows)
    return {"start": start, "end": end, "observations": len(rows), "observed_days": dict(by_day),
            "providers": dict(Counter(r[1] for r in rows)), "actual_shadow_trade_rows": trades,
            "after_due_forecasts": sum(created >= due for _,_,_,created,due in forecasts),
            "forecast_rows": len(forecasts), "counterfactual": liquidity_counterfactual(records),
            "replay_rows": records, "executable_replay_verified": False,
            "limitations": ["Sparse preserved observations lack full minute OHLC and first-receipt provenance.",
                            "Historical missing bars and quote depth cannot be reconstructed.",
                            "No inferred fills, return on allocated capital, drawdown or missed-rebound count."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily", required=True, type=Path)
    parser.add_argument("--legacy-db", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    bars = load_daily(args.daily)
    events = volume_events(bars)
    output = {"symbol": "ZPTA", "paper_only": True,
              "daily_sha256": hashlib.sha256(args.daily.read_bytes()).hexdigest(),
              "daily_sessions": len(bars), "last_daily_date": bars[-1]["date"],
              "entry_volume": {"cohorts": summarize(events), "week_bootstrap": bootstrap_rate_diff(events)},
              "daily_1pct": independent_daily(bars, .01), "daily_2_5pct": independent_daily(bars, .025)}
    if args.legacy_db:
        output["legacy_replay"] = legacy_replay(args.legacy_db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: output[k] for k in ("symbol", "paper_only", "daily_sha256", "daily_sessions", "last_daily_date")}))


if __name__ == "__main__":
    main()
