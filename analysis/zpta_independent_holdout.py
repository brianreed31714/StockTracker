"""Independent event selection and transparent holdout comparison for daily swing research.

Read-only analysis. Inputs are PR #6-style events, already generated from
completed daily bars; this module never simulates execution or places orders.
"""
from __future__ import annotations

import math
import statistics


def select_nonoverlapping(events, *, split_index=None, segment="all", embargo_sessions=0):
    """Select events chronologically; a position occupies entry..exit inclusive.

    A training event cannot exit on/after split_index; a holdout event must
    have its signal at/after split_index. Selection is per signal and horizon,
    not a portfolio optimizer. Ties are ordered deterministically.\n    embargo_sessions excludes events near the train/holdout boundary on both\n    sides; this is a conservative research restriction, not a CI guarantee.
    """
    if not isinstance(embargo_sessions, int) or embargo_sessions < 0:\n        raise ValueError("embargo_sessions must be a nonnegative integer")\n    if segment not in {"all", "training", "holdout"}:
        raise ValueError("invalid segment")
    if segment != "all" and (split_index is None or split_index < 0):
        raise ValueError("split_index required")
    chosen, occupied_until = [], -1
    for ev in sorted(events, key=lambda e: (e["signal_index"], e["exit_index"])):
        signal, exit_ = ev["signal_index"], ev["exit_index"]
        entry = signal + 1
        if exit_ < entry:
            raise ValueError("exit must not precede entry")
        if segment == "training" and exit_ >= split_index - embargo_sessions:
            continue
        if segment == "holdout" and signal < split_index + embargo_sessions:
            continue
        if entry <= occupied_until:
            continue
        chosen.append(ev)
        occupied_until = exit_
    return chosen


def evaluate(events):
    """Descriptive independent-event statistics; not portfolio ROI or proof of edge."""
    returns = [float(e["net_return_pct"]) for e in events]
    if not returns:
        return {"n": 0, "mean_net_pct": None, "win_fraction": None,
                "mean_ci95_pct": None, "compounded_trade_return_pct": None,
                "max_trade_sequence_drawdown_pct": None}
    n = len(returns)
    mean = statistics.mean(returns)
    # Normal approximation is exploratory, not valid for tiny or dependent cohorts.
    ci = None if n < 30 else [mean - 1.96 * statistics.stdev(returns) / math.sqrt(n),
                              mean + 1.96 * statistics.stdev(returns) / math.sqrt(n)]
    equity, peak, max_dd = 1.0, 1.0, 0.0
    for ret in returns:
        equity *= (1 + ret / 100)
        peak = max(peak, equity)
        max_dd = max(max_dd, 100 * (1 - equity / peak))
    return {"n": n, "mean_net_pct": round(mean, 4),
            "win_fraction": round(sum(x > 0 for x in returns) / n, 4),
            "mean_ci95_pct": [round(x, 4) for x in ci] if ci else None,
            "compounded_trade_return_pct": round(100 * (equity - 1), 4),
            "max_trade_sequence_drawdown_pct": round(max_dd, 4)}
