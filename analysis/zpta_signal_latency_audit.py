"""Read-only audit of when ZPTA predictions became knowable.

Usage: python analysis/zpta_signal_latency_audit.py analysis/evidence/*/zpta_predictions.csv

This checks research timestamp integrity only. It does not backtest fills,
connect to a broker, or change trader configuration.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def parse_timestamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Prediction timestamps must include an explicit timezone")
    return dt


def audit(files: list[Path], max_signal_age_seconds: float = 60.0) -> dict:
    if max_signal_age_seconds < 0:
        raise ValueError("max_signal_age_seconds must be nonnegative")
    horizon_counts = defaultdict(lambda: Counter({
        "predictions": 0, "created_after_due": 0, "stale_reference_price": 0,
        "bar_older_than_hour": 0, "due_mismatch": 0, "future_bar_timestamp": 0
    }))
    latencies = []
    distinct_events = set()
    distinct_horizons = set()
    late_examples = []
    files_read = 0
    for path in files:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            required = {"bar_ts", "created_ts", "due_ts", "horizon_minutes", "model"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError(f"Missing required columns in {path}")
            files_read += 1
            for row in reader:
                if not row.get("bar_ts"):
                    continue
                bar_ts = parse_timestamp(row["bar_ts"])
                created_ts = parse_timestamp(row["created_ts"])
                due_ts = parse_timestamp(row["due_ts"])
                horizon = int(row["horizon_minutes"])
                if horizon <= 0:
                    raise ValueError(f"Invalid prediction horizon in {path}")
                latency = (created_ts - bar_ts).total_seconds()
                h = horizon_counts[horizon]
                h["predictions"] += 1
                if created_ts >= due_ts:
                    h["created_after_due"] += 1
                    if len(late_examples) < 5:
                        late_examples.append({"bar_ts": bar_ts.isoformat(), "created_ts": created_ts.isoformat(),
                                              "due_ts": due_ts.isoformat(), "horizon_minutes": horizon})
                if latency > max_signal_age_seconds:
                    h["stale_reference_price"] += 1
                if latency >= 3600:
                    h["bar_older_than_hour"] += 1
                if abs((due_ts - (bar_ts + timedelta(minutes=horizon))).total_seconds()) > 1:
                    h["due_mismatch"] += 1
                if latency < 0:
                    h["future_bar_timestamp"] += 1
                latencies.append(latency)
                distinct_events.add(bar_ts.isoformat())
                distinct_horizons.add((bar_ts.isoformat(), horizon))
    by_horizon = {str(k): dict(v) for k, v in sorted(horizon_counts.items())}
    total = sum(v["predictions"] for v in horizon_counts.values())
    past_due = sum(v["created_after_due"] for v in horizon_counts.values())
    stale = sum(v["stale_reference_price"] for v in horizon_counts.values())
    issues = []
    if past_due:
        issues.append("PREDICTIONS_CREATED_AFTER_OUTCOME_DUE")
    if stale:
        issues.append("SIGNALS_USE_STALE_REFERENCE_PRICE")
    if any(v["due_mismatch"] for v in horizon_counts.values()):
        issues.append("DUE_TIMESTAMP_INCONSISTENT")
    if any(v["future_bar_timestamp"] for v in horizon_counts.values()):
        issues.append("FUTURE_BAR_TIMESTAMP")
    return {
        "status": "BLOCK_LIVE_VALIDATION" if issues else ("NO_DATA" if not total else "TIMESTAMPS_PLAUSIBLE_ONLY"),
        "files_read": files_read, "prediction_rows": total,
        "distinct_bar_timestamps": len(distinct_events),
        "distinct_bar_horizon_pairs": len(distinct_horizons),
        "median_signal_age_minutes": round(statistics.median(latencies) / 60, 3) if latencies else None,
        "created_after_due": past_due, "created_after_due_fraction": round(past_due / total, 4) if total else None,
        "reference_price_stale": stale, "by_horizon": by_horizon,
        "examples": late_examples, "issues": issues,
        "interpretation": "Signal age measures bar_ts->created_ts, not quote/trade execution latency. "
                          "Multiple model labels or horizons per bar are correlated observations, not independent trades. "
                          "A plausible timestamp is necessary, not sufficient, for a tradable signal."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--max-signal-age-seconds", type=float, default=60)
    parser.add_argument("--fail-on-hindsight", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.files, args.max_signal_age_seconds)
    formatted = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted, encoding="utf-8")
    else:
        print(formatted, end="")
    return 2 if args.fail_on_hindsight and report["status"] != "TIMESTAMPS_PLAUSIBLE_ONLY" else 0


if __name__ == "__main__":
    raise SystemExit(main())
