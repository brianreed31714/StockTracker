"""Fail-closed, research-only ZPTA completed-day prospective signal snapshot.

No broker, execution, credentials, historical-low entry, or trade activation.
Freeze the candidate after an as-of session and later score 1/3/5-session
outcomes separately. Provider data and corporate-action adjustments remain
UNVERIFIED until independently reconciled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from analysis.zpta_daily_swing_research import daily_signals, _rsi
from analysis.zpta_intraday_recovery import load_daily

EASTERN = ZoneInfo("America/New_York")
SIGNAL_RULESET = "ZPTA_DAILY_V1_FROZEN_2026_10_22"
HORIZONS = (1, 3, 5)


def make_snapshot(bars, *, as_of, retrieved_utc, source,
                  min_turnover=25000.0, provider_last_date=None):
    """Build a timestamped, no-future-bar snapshot, not an executable signal."""
    target = date.fromisoformat(as_of)
    retrieved = datetime.fromisoformat(retrieved_utc.replace("Z", "+00:00"))
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise ValueError("Source retrieval timestamp must have a timezone")
    observed = retrieved.astimezone(EASTERN)
    if observed.date() < target:
        raise ValueError("Retrieval predates as-of date")
    if observed < datetime.combine(target, time(16, 30), EASTERN):
        raise ValueError("Not enough post-close data-settlement time")
    if min_turnover < 0:
        raise ValueError("Invalid turnover floor")
    if not source.strip():
        raise ValueError("Missing data provenance")
    if not bars or len(bars) < 11:
        raise ValueError("Need at least eleven daily observations")
    dates = [b["date"] for b in bars]
    if dates != sorted(set(dates)):
        raise ValueError("Duplicate or unsorted daily dates")
    if dates[-1] != as_of:
        raise ValueError("STALE_OR_FUTURE_SOURCE: latest bar must equal as-of")
    if provider_last_date is not None and provider_last_date != as_of:
        raise ValueError("Metadata last_date disagrees with as-of")
    if any(min(b["open"], b["high"], b["low"], b["close"]) <= 0 or
           b["high"] < max(b["open"], b["low"], b["close"]) or
           b["low"] > min(b["open"], b["close"]) or b["volume"] < 0
           for b in bars):
        raise ValueError("Invalid daily OHLCV")
    b = bars[-1]
    prior = bars[-2]
    ten_high = max(x["high"] for x in bars[-11:-1])
    flags = daily_signals(bars, len(bars)-1)
    turnover = b["close"] * b["volume"]
    liquid = b["volume"] > 0 and turnover >= min_turnover
    changes = {
        "close_change_pct": round((b["close"]/prior["close"]-1)*100, 4),
        "low_from_previous_close_pct": round((b["low"]/prior["close"]-1)*100, 4),
        "low_to_close_recovery_pct": round((b["close"]/b["low"]-1)*100, 4),
        "close_below_prior_ten_day_high_pct": round((b["close"]/ten_high-1)*100, 4),
        "rsi3": round(_rsi([x["close"] for x in bars]), 4),
    }
    # Hash input data rather than committing licensed raw OHLCV.
    canonical = json.dumps(bars, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "symbol": "ZPTA", "as_of": as_of,
        "retrieved_utc": retrieved.isoformat(), "source": source,
        "snapshot_type": ("SAME_DAY_POST_CLOSE_CANDIDATE"
                          if observed.date() == target
                          else "HISTORICAL_REPLAY_NOT_PROSPECTIVE"),
        "ruleset": SIGNAL_RULESET,
        "input_ohlcv_sha256": digest,
        "history_sessions": len(bars),
        "reference_close": b["close"],
        "reference_low": b["low"],
        "reference_volume": b["volume"],
        "dollar_turnover_proxy": round(turnover, 2),
        "min_turnover_proxy": min_turnover,
        "research_liquidity_gate_pass": liquid,
        "features": changes,
        "completed_day_signal_flags": flags,
        "research_candidate": bool(flags and liquid),
        "candidate_status": ("RESEARCH_CANDIDATE_UNVERIFIED"
                             if flags and liquid else "NO_QUALIFYING_RESEARCH_ENTRY"),
        "next_session_entry": "NOT_OBSERVED",
        "future_outcomes": {f"{h}d": None for h in HORIZONS},
        "independent_price_volume_reconciliation_verified": False,
        "historical_corporate_action_adjustment_verified": False,
        "broker_otc_quote_tradability_verified": False,
        "real_money_trading_allowed": False,
        "limitations": [
            "The low-to-close rebound is hindsight description, NOT a buy at the low.",
            "No prediction of a future low or profitable rebound is established.",
            "Printed daily prices and close-times do not prove executable bid/ask fills.",
            "The $25k turnover floor is a proxy, not order-book liquidity.",
            "Historical holdout was examined; new observations must be scored prospectively.",
            "No live orders, risk-rule changes, broker access, or model promotion.",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("daily_csv", type=Path)
    p.add_argument("--metadata", type=Path, required=True)
    p.add_argument("--as-of", required=True)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    meta = json.loads(args.metadata.read_text(encoding="utf-8"))
    if meta.get("symbol") != "ZPTA":
        raise ValueError("Incorrect provider symbol")
    if meta.get("status") != "SOURCE_CANDIDATE_REQUIRES_INDEPENDENT_RECONCILIATION":
        raise ValueError("Unexpected provider status")
    result = make_snapshot(
        load_daily(args.daily_csv), as_of=args.as_of,
        retrieved_utc=meta["retrieved_utc"],
        source=meta["source"], provider_last_date=meta.get("last_date"))
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # No overwriting a frozen dated prospective snapshot.
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
