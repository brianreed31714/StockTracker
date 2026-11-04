"""Read-only audit: did a revised preceding daily bar change today's ZPTA signal?

The alternate close/volume must come from a previously recorded dated source,
not an optimized parameter. No broker orders, no live signals, no raw data saved.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from analysis.zpta_daily_swing_research import daily_signals, _rsi
from analysis.zpta_intraday_recovery import load_daily


def audit_previous_revision(bars, *, signal_date, frozen_previous_date,
                            frozen_previous_close, frozen_previous_volume):
    dates = [b["date"] for b in bars]
    if len(bars) < 11 or dates != sorted(set(dates)):
        raise ValueError("Require at least eleven sorted unique completed daily bars")
    if dates[-1] != signal_date or dates[-2] != frozen_previous_date:
        raise ValueError("Only latest completed day and its immediately preceding session")
    if (not math.isfinite(frozen_previous_close) or frozen_previous_close <= 0
            or not isinstance(frozen_previous_volume, int)
            or frozen_previous_volume < 0):
        raise ValueError("Invalid frozen previous close or volume")
    prev = bars[-2]
    if not prev["low"] <= frozen_previous_close <= prev["high"]:
        raise ValueError("Frozen close outside revised previous-day high-low range")
    # Never modify the input series. The alternate is a counterfactual using
    # the previously frozen published close, not a second verified dataset.
    alternate = [dict(b) for b in bars]
    alternate[-2]["close"] = frozen_previous_close
    alternate[-2]["volume"] = frozen_previous_volume
    latest_flags = daily_signals(bars, len(bars)-1)
    frozen_flags = daily_signals(alternate, len(alternate)-1)
    latest_rsi = _rsi([b["close"] for b in bars])
    frozen_rsi = _rsi([b["close"] for b in alternate])
    changed = (not math.isclose(prev["close"], frozen_previous_close, rel_tol=1e-8)
               or int(prev["volume"]) != frozen_previous_volume)
    flags_changed = latest_flags != frozen_flags
    return {
        "symbol": "ZPTA",
        "signal_date": signal_date,
        "frozen_previous_date": frozen_previous_date,
        "latest_previous_close": prev["close"],
        "frozen_previous_close": frozen_previous_close,
        "latest_previous_volume": prev["volume"],
        "frozen_previous_volume": frozen_previous_volume,
        "previous_bar_revision_detected": changed,
        "latest_signal_flags": latest_flags,
        "frozen_previous_close_signal_flags": frozen_flags,
        "latest_rsi3": round(latest_rsi, 4),
        "frozen_previous_close_rsi3": round(frozen_rsi, 4),
        "signals_changed_by_previous_bar_revision": flags_changed,
        "source_quality_status": (
            "REVISION_CHANGED_SIGNAL_DO_NOT_PROMOTE" if flags_changed else
            "PREVIOUS_BAR_REVISION_REQUIRES_RECONCILIATION" if changed else
            "NO_PREVIOUS_BAR_REVISION_DETECTED_NOT_FULLY_VERIFIED"
        ),
        "full_history_corporate_actions_verified": False,
        "broker_fill_verified": False,
        "real_money_trading_allowed": False,
        "limitations": [
            "The alternate uses a recorded prior source close, not a new validated market observation.",
            "One unchanged/reconciled day does not validate the full history or executable OTC quotes.",
            "No future outcomes, fills or low-price executions are inferred.",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("daily_csv", type=Path)
    p.add_argument("--signal-date", required=True)
    p.add_argument("--frozen-previous-date", required=True)
    p.add_argument("--frozen-previous-close", type=float, required=True)
    p.add_argument("--frozen-previous-volume", type=int, required=True)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = audit_previous_revision(
        load_daily(args.daily_csv), signal_date=args.signal_date,
        frozen_previous_date=args.frozen_previous_date,
        frozen_previous_close=args.frozen_previous_close,
        frozen_previous_volume=args.frozen_previous_volume)
    payload = json.dumps(result, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
