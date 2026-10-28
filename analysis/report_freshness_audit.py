#!/usr/bin/env python3
"""Read-only audit of published StockTracker paper-research evidence.

This script never touches broker credentials, submits orders, or mutates runtime
state. Pass the last *completed* exchange session explicitly to avoid treating
weekends and exchange holidays as missing reports.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
from pathlib import Path


def audit(root: Path, expected_session: str) -> dict:
    date.fromisoformat(expected_session)
    errors, warnings = [], []
    report_path = root / "analysis/performance/latest.json"
    if not report_path.is_file():
        return {"status": "FAIL", "expected_session": expected_session,
                "errors": ["MISSING_LATEST_REPORT"], "warnings": []}

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        metrics = report["metrics"]
        published = str(metrics["review_date"])
        if date.fromisoformat(published).isoformat() != published:
            raise ValueError("noncanonical review_date")
    except (ValueError, KeyError, TypeError) as exc:
        return {"status": "FAIL", "expected_session": expected_session,
                "errors": ["INVALID_LATEST_REPORT: " + str(exc)], "warnings": []}

    if published != expected_session:
        errors.append("STALE_REPORT: expected " + expected_session + ", got " + published)
    if metrics.get("paper_only") is not True:
        errors.append("PAPER_ONLY_NOT_CONFIRMED")

    manifest_path = root / "analysis/evidence" / published / "manifest.json"
    if not manifest_path.is_file():
        errors.append("MISSING_EVIDENCE_MANIFEST")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("review_date") != published:
                errors.append("MANIFEST_DATE_MISMATCH")
            integrity = manifest.get("integrity_analysis") or {}
            if integrity.get("status") != "PASS" or integrity.get("issues"):
                errors.append("EVIDENCE_INTEGRITY_NOT_PASS")
            for table in integrity.get("empty_tables") or []:
                warnings.append("EMPTY_RESEARCH_TABLE: " + str(table))
        except (ValueError, TypeError):
            errors.append("INVALID_EVIDENCE_MANIFEST")

    config = metrics.get("config") or {}
    if "NBIS" not in (config.get("trade_symbols") or []):
        warnings.append("NBIS_NOT_IN_REPORTED_RUNTIME_UNIVERSE")

    # This is deliberately not called account P/L or an account equity curve:
    # only realized rows from published, dated evidence are observable here.
    evidence_root = root / "analysis/evidence"
    pnl, row_count, sessions = Decimal("0"), 0, []
    seen = {}
    invalid_realized_evidence = False
    for csv_path in sorted(evidence_root.glob("????-??-??/realized.csv")):
        session_date = csv_path.parent.name
        # Never let later session files leak into an earlier published EOD report.
        if session_date > published or session_date > expected_session:
            warnings.append("FUTURE_REALIZED_EVIDENCE_EXCLUDED: " + session_date)
            continue
        try:
            with csv_path.open(encoding="utf-8", newline="") as stream:
                for row in csv.DictReader(stream):
                    key = (row.get("id"), row.get("ts"))
                    if not all(isinstance(x, str) and x.strip() for x in key):
                        raise ValueError("missing realized row id or timestamp")
                    # Folder placement alone does not establish the trade's session.
                    # UTC midnight may still belong to the prior New York session.
                    stamp = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
                    if stamp.tzinfo is None or stamp.utcoffset() is None:
                        raise ValueError("realized timestamp must include a timezone")
                    trade_session = stamp.astimezone(ZoneInfo("America/New_York")).date().isoformat()
                    if trade_session != session_date:
                        raise ValueError("realized trade session mismatch: " + trade_session + " != " + session_date)
                    value = Decimal(str(row["pnl"]))
                    if not value.is_finite():
                        raise InvalidOperation("non-finite realized P/L")
                    fingerprint = (value, row.get("symbol"))
                    if key in seen:
                        if seen[key] != fingerprint:
                            invalid_realized_evidence = True
                            errors.append("CONFLICTING_DUPLICATE_REALIZED_ROW: " + str(key))
                        else:
                            warnings.append("DUPLICATE_REALIZED_ROW: " + str(key))
                        continue
                    seen[key] = fingerprint
                    pnl += value
                    row_count += 1
            sessions.append(csv_path.parent.name)
        except (OSError, KeyError, InvalidOperation, ValueError) as exc:
            invalid_realized_evidence = True
            errors.append("INVALID_REALIZED_CSV: " + str(csv_path) + ": " + str(exc))

    if not sessions:
        warnings.append("MISSING_REALIZED_EVIDENCE_NOT_ZERO_PNL")
    warnings.append("ACCOUNT_EQUITY_RETURN_AND_DRAWDOWN_NOT_VERIFIABLE_FROM_PUBLISHED_EVIDENCE")
    return {
        "status": "FAIL" if errors else "WARN" if warnings else "PASS",
        "expected_session": expected_session,
        "published_session": published,
        "published_realized_pnl_usd_observed_only": (
            str(pnl.quantize(Decimal("0.01"))) if sessions and not invalid_realized_evidence else None
        ),
        "realized_evidence_status": (
            "INVALID" if invalid_realized_evidence else "OBSERVED_ONLY" if sessions else "MISSING"
        ),
        "published_realized_row_count": row_count,
        "published_sessions_with_realized_file": sessions,
        "account_equity_return_available": False,
        "account_max_drawdown_available": False,
        "errors": errors,
        "warnings": sorted(set(warnings)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-session", required=True,
                        help="YYYY-MM-DD of the last completed NYSE session")
    args = parser.parse_args()
    result = audit(args.root, args.expected_session)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
