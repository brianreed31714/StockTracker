"""ZPTA six-month down-streak study. Research only; single Yahoo chart provider.

No fills or profitability implied. Noon = 12:00 ET 60-minute bar OPEN (not
the 12:00-12:59 close). Missing bars are never interpolated.
"""
import argparse
import csv
import json
import math
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
BASE = "https://query1.finance.yahoo.com/v8/finance/chart/ZPTA"


def fetch(interval):
    url = BASE + "?range=6mo&interval=" + interval + "&events=splits"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)
    if payload.get("chart", {}).get("error"):
        raise RuntimeError(str(payload["chart"]["error"]))
    result = payload["chart"]["result"][0]
    quotes = result["indicators"]["quote"][0]
    bars = []
    for i, stamp in enumerate(result.get("timestamp", [])):
        bar = {k: quotes[k][i] for k in ("open", "high", "low", "close", "volume")}
        if bar["close"] is None:
            continue
        bar["time"] = datetime.fromtimestamp(stamp, NY)
        bars.append(bar)
    return bars, result.get("events", {}).get("splits", {})


def build_rows(daily, hourly):
    noon = {}
    for b in hourly:
        t = b["time"]
        if t.hour == 12 and t.minute == 0 and b["open"] is not None:
            noon[t.date().isoformat()] = b["open"]
    # Require chronological dates and actual observed next session.
    dates = sorted({b["time"].date().isoformat(): b for b in daily}.items())
    rows = []
    for i in range(1, len(dates)-1):
        date, today = dates[i]
        _, previous = dates[i-1]
        next_date, nxt = dates[i+1]
        p = previous["close"]
        c = today["close"]
        nc = nxt["close"]
        if not all(isinstance(v, (int, float)) and v > 0 and math.isfinite(v)
                   for v in (p, c, nc)):
            continue
        # Consecutive negative closing changes ending on signal day.
        streak = 0
        j = i
        while j > 0 and dates[j][1]["close"] < dates[j-1][1]["close"]:
            streak += 1
            j -= 1
        np = noon.get(next_date)
        rows.append({
            "date": date, "close": c, "close_change_pct": 100*(c/p-1),
            "down_streak": streak, "next_date": next_date,
            "next_noon_price": np,
            "next_noon_vs_signal_close_pct": 100*(np/c-1) if np else None,
            "next_eod_price": nc,
            "next_eod_vs_signal_close_pct": 100*(nc/c-1),
            "next_eod_vs_noon_pct": 100*(nc/np-1) if np else None,
        })
    return rows


def stats(rows, key):
    vals = [r[key] for r in rows if r[key] is not None]
    n = len(vals)
    wins = sum(v > 0 for v in vals)
    return {"n": n, "up_count": wins, "up_rate": wins/n if n else None,
            "mean_pct": sum(vals)/n if n else None,
            "median_pct": sorted(vals)[n//2] if n % 2 else
              ((sorted(vals)[n//2-1]+sorted(vals)[n//2])/2 if n else None)}


def analyze(rows):
    cohorts = {"all": rows, "down_2_exact": [r for r in rows if r["down_streak"] == 2],
               "down_3_exact": [r for r in rows if r["down_streak"] == 3],
               "down_2_or_3_exact": [r for r in rows if r["down_streak"] in (2, 3)],
               "down_at_least_2": [r for r in rows if r["down_streak"] >= 2]}
    return {name: {
        "noon_vs_prior_close": stats(group, "next_noon_vs_signal_close_pct"),
        "eod_vs_prior_close": stats(group, "next_eod_vs_signal_close_pct"),
        "eod_vs_noon": stats(group, "next_eod_vs_noon_pct"),
    } for name, group in cohorts.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("analysis/performance/zpta_down_streak_6mo"))
    args = parser.parse_args()
    daily, daily_splits = fetch("1d")
    hourly, hourly_splits = fetch("60m")
    if not daily or not hourly:
        raise RuntimeError("Missing daily or hourly bars; refusing partial result")
    rows = build_rows(daily, hourly)
    if not rows:
        raise RuntimeError("No complete paired sessions")
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "daily_comparison.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = {"symbol": "ZPTA", "source": "Yahoo Finance chart API only",
              "as_of_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
              "daily_bars": len(daily), "hourly_bars": len(hourly),
              "paired_sessions": len(rows), "noon_observed": sum(r["next_noon_price"] is not None for r in rows),
              "split_events_daily": daily_splits, "split_events_hourly": hourly_splits,
              "summary": analyze(rows),
              "cautions": [
                  "Single-source exploratory study, not independent corporate-action verification.",
                  "Noon price is the 12:00 ET hourly bar OPEN, not its close or an executable quote.",
                  "Noon missing data excluded only from noon cohorts; never fabricated.",
                  "Next-day outcomes measured from prior close, not achievable entry returns.",
                  "Compare conditional up-rates to all eligible days; small cohorts and serial dependence can mislead.",
                  "No OTC bid/ask, spreads, liquidity execution, or trading authorization.",
              ]}
    (args.out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
