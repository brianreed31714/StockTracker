"""ZPTA daily dip/recovery research. Offline, read-only, no broker access.

Usage: python analysis/zpta_dip_recovery.py path/to/zpta_daily.csv
CSV columns: date,open,high,low,close,volume (case-insensitive).
Historical bars must be adjusted consistently for splits; this script does not fetch data.
"""
import argparse
import csv
import json
import statistics
from datetime import date
from pathlib import Path


def load_bars(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    bars = []
    for raw in rows:
        r = {k.strip().lower(): v for k, v in raw.items() if k}
        day = date.fromisoformat(r["date"][:10])
        bar = {"date": day.isoformat()}
        for field in ("open", "high", "low", "close", "volume"):
            bar[field] = float(r[field])
        if min(bar["open"], bar["high"], bar["low"], bar["close"]) <= 0 or bar["volume"] < 0:
            raise ValueError(f"Invalid OHLCV on {day}")
        if bar["low"] > min(bar["open"], bar["close"]) or bar["high"] < max(bar["open"], bar["close"]):
            raise ValueError(f"Inconsistent OHLC on {day}")
        bars.append(bar)
    bars.sort(key=lambda b: b["date"])
    if len({b["date"] for b in bars}) != len(bars):
        raise ValueError("Duplicate trading dates")
    return bars


def mean(values):
    return round(statistics.mean(values), 6) if values else None


def median(values):
    return round(statistics.median(values), 3) if values else None


def study(bars, thresholds=(0.05, 0.10, 0.15), horizons=(1, 2, 3, 5)):
    results = {"sessions": len(bars), "start": bars[0]["date"] if bars else None,
               "end": bars[-1]["date"] if bars else None, "thresholds": {}}
    for threshold in thresholds:
        events = []
        # Signal is determined from the day's closing price only; future returns start next session.
        for i in range(1, len(bars)):
            previous, current = bars[i - 1], bars[i]
            change = current["close"] / previous["close"] - 1
            if change > -threshold:
                continue
            event = {"date": current["date"], "dip_pct": round(change * 100, 3)}
            for h in horizons:
                event[f"return_{h}d_pct"] = (
                    round((bars[i + h]["close"] / current["close"] - 1) * 100, 3)
                    if i + h < len(bars) else None
                )
            # Recover half/full of close-to-close decline using subsequent daily closes.
            lost = previous["close"] - current["close"]
            for fraction, label in ((0.5, "half"), (1.0, "full")):
                target = current["close"] + fraction * lost
                event[f"{label}_recovery_sessions"] = next(
                    (j - i for j in range(i + 1, len(bars)) if bars[j]["close"] >= target), None
                )
            events.append(event)
        summary = {"events": len(events), "overlapping_events_possible": True}
        for h in horizons:
            valid = [e[f"return_{h}d_pct"] for e in events if e[f"return_{h}d_pct"] is not None]
            summary[f"{h}d"] = {"observations": len(valid), "mean_return_pct": mean(valid),
                                "median_return_pct": median(valid),
                                "positive_fraction": round(sum(v > 0 for v in valid) / len(valid), 4) if valid else None}
        for label in ("half", "full"):
            observed = [e[f"{label}_recovery_sessions"] for e in events if e[f"{label}_recovery_sessions"] is not None]
            summary[f"{label}_recovery"] = {
                "recovered": len(observed), "not_recovered_by_dataset_end": len(events) - len(observed),
                "median_sessions_if_recovered": median(observed),
                "fraction_recovered_within_1d": round(sum(v <= 1 for v in observed) / len(events), 4) if events else None,
                "fraction_recovered_within_5d": round(sum(v <= 5 for v in observed) / len(events), 4) if events else None}
        results["thresholds"][f"{threshold:.0%}"] = {"summary": summary, "events": events}
    results["limitations"] = [
        "Descriptive analysis only; not a trade backtest or profitability estimate.",
        "Closing-price recovery differs from intraday recovery.",
        "Overlapping dip events are not independent.",
        "Recovery times are right-censored at dataset end.",
        "No spread, slippage, fees, borrow constraints or fill assumptions.",
        "Verify corporate-action adjustments and OTC symbol/history continuity before interpreting results."
    ]
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = study(load_bars(args.csv_path))
    output = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
