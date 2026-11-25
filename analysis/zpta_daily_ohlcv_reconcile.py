"""Fail-closed cross-provider daily ZPTA OHLCV audit (research only).

A close/volume match is not enough to validate next-open entry scenarios:
open, high and low must be reconciled as well. Daily prints are NOT executable
broker quotes. This module never marks corporate actions or fills verified.
"""
from __future__ import annotations

from datetime import date, datetime
import math

FIELDS = ("open", "high", "low", "close", "volume")
DEFAULT_TOLERANCE_PCT = {"open": 0.5, "high": 0.5, "low": 0.5,
                         "close": 0.5, "volume": 5.0}


def _validate_series(bars, source):
    if not source or not source.strip():
        raise ValueError("Named source required")
    if not isinstance(bars, list) or not bars:
        raise ValueError("Nonempty daily series required")
    seen = set()
    previous = None
    for b in bars:
        d = b["date"]
        if not isinstance(d, str) or date.fromisoformat(d).isoformat() != d:
            raise ValueError("Invalid ISO date")
        if d in seen or (previous is not None and d <= previous):
            raise ValueError("Duplicate or nonchronological dates")
        seen.add(d)
        previous = d
        vals = [b[f] for f in FIELDS]
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or
               not math.isfinite(x) for x in vals):
            raise ValueError("Invalid numeric OHLCV")
        o, h, l, c, v = vals
        if min(o, h, l, c) <= 0 or v < 0 or int(v) != v or h < max(o, l, c) or l > min(o, c):
            raise ValueError("Invalid OHLCV ordering/volume")


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Source retrieval timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Source retrieval timestamp must be timezone-aware")
    return value


def reconcile(candidate, reference, *, candidate_source, reference_source,
              candidate_retrieved_utc, reference_retrieved_utc,
              tolerance_pct=None):
    """Compare all available dates/fields; fail closed for any mismatch or gap.

    Both series must be date-ordered and have timestamped retrievals.
    The reference is independent, not proof of its accuracy.
    """
    if candidate_source.strip() == reference_source.strip():
        raise ValueError("Independent distinct source names required")
    _validate_series(candidate, candidate_source)
    _validate_series(reference, reference_source)
    _timestamp(candidate_retrieved_utc)
    _timestamp(reference_retrieved_utc)
    tol = dict(DEFAULT_TOLERANCE_PCT)
    if tolerance_pct is not None:
        if set(tolerance_pct) != set(FIELDS):
            raise ValueError("Tolerance must cover every OHLCV field")
        tol = dict(tolerance_pct)
    if any(not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0
           for x in tol.values()):
        raise ValueError("Invalid tolerance")
    a, b = ({row["date"]: row for row in seq} for seq in (candidate, reference))
    dates = sorted(set(a) | set(b))
    audited = []
    mismatch_dates = []
    missing_dates = []
    zero_volume_dates = []
    for d in dates:
        if d not in a or d not in b:
            missing_dates.append(d)
            audited.append({"date": d, "status": "DATE_MISSING_IN_ONE_SOURCE",
                            "missing_from": ("candidate" if d not in a else "reference")})
            continue
        diffs = {f: round(100 * abs(a[d][f] - b[d][f]) / b[d][f], 6)
                 if b[d][f] != 0 else (0.0 if a[d][f] == 0 else float("inf"))
                 for f in FIELDS}
        mismatched = [f for f in FIELDS if diffs[f] > tol[f]]
        if a[d]["volume"] == 0 or b[d]["volume"] == 0:
            zero_volume_dates.append(d)
        status = ("FIELD_MISMATCH_DO_NOT_PROMOTE" if mismatched else
                  "ZERO_VOLUME_UNTRADABLE" if d in zero_volume_dates else
                  "SAMPLE_MATCH_NOT_FULLY_VERIFIED")
        if mismatched:
            mismatch_dates.append(d)
        audited.append({"date": d, "status": status, "mismatched_fields": mismatched,
                        "difference_pct": diffs,
                        "candidate_turnover_proxy": round(a[d]["close"] * a[d]["volume"], 2),
                        "reference_turnover_proxy": round(b[d]["close"] * b[d]["volume"], 2)})
    status = ("OHLCV_MISMATCH_OR_MISSING_DO_NOT_PROMOTE"
              if mismatch_dates or missing_dates else
              "ZERO_VOLUME_REQUIRES_EXCLUSION" if zero_volume_dates else
              "SAMPLE_MATCH_NOT_FULL_HISTORY_VERIFIED")
    return {
        "symbol": "ZPTA", "candidate_source": candidate_source,
        "reference_source": reference_source,
        "candidate_retrieved_utc": candidate_retrieved_utc,
        "reference_retrieved_utc": reference_retrieved_utc,
        "dates_compared": len(dates) - len(missing_dates),
        "mismatch_dates": mismatch_dates,
        "missing_dates": missing_dates,
        "zero_volume_dates": zero_volume_dates,
        "rows": audited,
        "status": status,
        "full_history_corporate_action_adjustments_verified": False,
        "executable_bid_ask_size_verified": False,
        "broker_fills_verified": False,
        "eligible_for_model_promotion": False,
        "real_money_trading_allowed": False,
        "limitations": [
            "Matching OHLCV samples do not certify a complete adjusted series or venue coverage.",
            "A price print is not an executable OTC bid/ask with available size.",
            "Do not substitute a source-favorable open or same-day low in a backtest.",
            "A source mismatch may reflect opening-print definitions, venues or revisions.",
        ],
    }
