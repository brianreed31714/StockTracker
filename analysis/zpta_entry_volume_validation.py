"""Read-only follow-on to ZPTA daily close study: next-open execution proxy and volume.

CSV columns: Date, Open, High, Low, Close, Adj Close, Volume.
Use exactly one source; don't merge conflicting provider bars.
"""
import argparse
import csv
import json
import math
import random
import statistics
from datetime import datetime
from pathlib import Path


def parse_price(value):
    return float(str(value).replace(",", "").strip())


def parse_date(value):
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported trading date: {value!r}")


def read_daily(path):
    records = []
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            records.append({
                "date": parse_date(row["Date"]),
                "open": parse_price(row["Open"]),
                "close": parse_price(row["Close"]),
                "volume": int(parse_price(row["Volume"])),
            })
    records.sort(key=lambda r: r["date"])
    if len({r["date"] for r in records}) != len(records):
        raise ValueError("Duplicate session date")
    if any(not math.isfinite(r["open"]) or not math.isfinite(r["close"]) or
           r["open"] <= 0 or r["close"] <= 0 or r["volume"] < 0 for r in records):
        raise ValueError("Invalid OHLCV")
    return records


def evaluate(bars):
    events = []
    for i in range(2, len(bars)-1):
        today, prior, nxt = bars[i], bars[i-1], bars[i+1]
        streak = 0
        j = i
        while j > 0 and bars[j]["close"] < bars[j-1]["close"]:
            streak += 1
            j -= 1
        volume_reference = [b["volume"] for b in bars[max(0, i-20):i]]
        baseline_volume = statistics.median(volume_reference) if len(volume_reference) >= 5 else None
        rel_volume = today["volume"] / baseline_volume if baseline_volume else None
        events.append({
            "date": today["date"], "close": today["close"],
            "change_pct": 100*(today["close"]/prior["close"]-1),
            "streak": streak, "signal_volume": today["volume"],
            "relative_volume": rel_volume,
            "next_date": nxt["date"], "next_open": nxt["open"],
            "next_close": nxt["close"],
            "next_close_vs_signal_close_pct": 100*(nxt["close"]/today["close"]-1),
            "next_open_gap_pct": 100*(nxt["open"]/today["close"]-1),
            "next_open_to_close_pct": 100*(nxt["close"]/nxt["open"]-1),
        })
    return events


def summarize(events):
    cohorts = {"all": events, "exact_2": [e for e in events if e["streak"] == 2],
               "exact_3": [e for e in events if e["streak"] == 3],
               "at_least_2": [e for e in events if e["streak"] >= 2],
               "2plus_low_volume": [e for e in events if e["streak"] >= 2 and e["relative_volume"] is not None and e["relative_volume"] < 1],
               "2plus_high_volume": [e for e in events if e["streak"] >= 2 and e["relative_volume"] is not None and e["relative_volume"] >= 1]}
    result = {}
    for name, cohort in cohorts.items():
        result[name] = {"count": len(cohort)}
        for key in ("next_close_vs_signal_close_pct", "next_open_to_close_pct", "next_open_gap_pct"):
            vals = [e[key] for e in cohort]
            result[name][key] = {
                "mean_pct": statistics.mean(vals) if vals else None,
                "median_pct": statistics.median(vals) if vals else None,
                "positive_count": sum(v > 0 for v in vals),
                "positive_rate": sum(v > 0 for v in vals)/len(vals) if vals else None}
    return result


def bootstrap_rate_diff(events, seed=20261104, iterations=2000):
    # Week-cluster resampling preserves some local serial dependence.
    weeks = {}
    for e in events:
        iso = datetime.fromisoformat(e["date"]).isocalendar()
        weeks.setdefault((iso.year, iso.week), []).append(e)
    blocks = list(weeks.values())
    if len(blocks) < 5 or not any(e["streak"] == 2 for e in events):
        return None
    rng = random.Random(seed)
    diffs = []
    for _ in range(iterations):
        sample = [e for _ in blocks for e in rng.choice(blocks)]
        down = [e for e in sample if e["streak"] == 2]
        if not down:
            continue
        diffs.append(sum(e["next_close_vs_signal_close_pct"] > 0 for e in down)/len(down)
                     -sum(e["next_close_vs_signal_close_pct"] > 0 for e in sample)/len(sample))
    if not diffs:
        return None
    diffs.sort()
    return {"point_estimate": sum(e["next_close_vs_signal_close_pct"] > 0 for e in events if e["streak"] == 2)/sum(e["streak"] == 2 for e in events)
            -sum(e["next_close_vs_signal_close_pct"] > 0 for e in events)/len(events),
            "ci_95": [diffs[int(.025*(len(diffs)-1))], diffs[int(.975*(len(diffs)-1))]],
            "method": "week-block bootstrap; exploratory"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    events = evaluate(read_daily(a.input))
    a.out.mkdir(parents=True, exist_ok=True)
    if events:
        with (a.out / "entry_volume_events.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(events[0]))
            w.writeheader()
            w.writerows(events)
    result = {"cohorts": summarize(events), "two_down_vs_baseline": bootstrap_rate_diff(events),
              "warnings": ["Next-open price is not guaranteed executable; OTC spread and size unknown.",
                           "Single source, corporate actions not independently validated.",
                           "Historical analysis is exploratory, not out-of-sample proof.",
                           "Noon and news correlation require separate datasets."]}
    (a.out / "entry_volume_summary.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
