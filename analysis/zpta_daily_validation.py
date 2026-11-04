"""Conservative, offline validation helpers for ZPTA completed-day research.

Never treat a daily LOW touch as proof a resting OTC limit order filled.
No broker connections, trade submission, or live strategy changes.
"""
from __future__ import annotations

import random
import statistics


def select_nonoverlapping(events):
    """Earliest-signal-first; exclude overlapping entry-to-exit holding windows.

    Each event requires integer entry_index and exit_index. Multiple simultaneous
    signals cannot be counted as independent portfolio trades.
    """
    chosen = []
    last_exit = -1
    for e in sorted(events, key=lambda x: (x["entry_index"], x["exit_index"])):
        start, end = int(e["entry_index"]), int(e["exit_index"])
        if start < 0 or end < start:
            raise ValueError("Invalid entry/exit indices")
        if start > last_exit:
            chosen.append(e)
            last_exit = end
    return chosen


def event_bootstrap_ci(returns_pct, seed=20261023, resamples=10000, confidence=0.95):
    """Simple iid event bootstrap; diagnostic only, NOT a time-series proof."""
    if resamples < 100 or not 0 < confidence < 1:
        raise ValueError("Invalid bootstrap settings")
    values = list(returns_pct)
    if not values:
        return {"events": 0, "mean_pct": None, "ci_pct": None, "warning": "NO_EVENTS"}
    if any(not isinstance(v, (int, float)) or not -float("inf") < v < float("inf") for v in values):
        raise ValueError("Nonfinite returns")
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n))/n for _ in range(resamples))
    lo = max(0, int((1-confidence)/2*resamples))
    hi = min(resamples-1, int((1+confidence)/2*resamples))
    return {
        "events": n,
        "mean_pct": round(statistics.mean(values), 4),
        "median_pct": round(statistics.median(values), 4),
        "ci_pct": [round(means[lo], 4), round(means[hi], 4)],
        "warning": "LOW_SAMPLE_AND_IID_ASSUMPTION" if n < 30 else "IID_EVENTS_ASSUMPTION",
    }


def next_day_limit_eligibility(signal_close, next_open, next_low, discount_pct=0.03):
    """Describe next-session price-based eligibility; do not assert fills.

    At next-day OPEN below limit: opening print is at or below hypothetical
    buy limit, but real fill/queue cannot be verified. Intraday low touches
    cannot prove fills or whether target/stop happened first.
    """
    if min(signal_close, next_open, next_low) <= 0 or next_low > next_open:
        raise ValueError("Invalid prices")
    if not 0 <= discount_pct < 1:
        raise ValueError("Invalid discount")
    limit = signal_close * (1-discount_pct)
    if next_open <= limit:
        status = "OPEN_PRINT_ELIGIBLE_FILL_UNVERIFIED"
    elif next_low <= limit:
        status = "LOW_TOUCHED_FILL_UNVERIFIED"
    else:
        status = "NOT_REACHED"
    return {
        "buy_limit": round(limit, 6),
        "status": status,
        "verified_fill": False,
        "tradable_return_pct": None,
    }
