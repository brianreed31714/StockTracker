#!/usr/bin/env python3
"""Publish a sanitized, row-complete StockTracker evidence bundle.

The local SQLite database and runtime logs remain the system of record. This
export contains every row used by the daily review for the selected market day,
plus sanitized state/feed snapshots and integrity checks. Secrets and raw
broker order identifiers are never published.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except ImportError:  # Keeps evidence export usable in minimal recovery environments.
    def load_dotenv(*_args, **_kwargs):
        return False

ROOT = Path(__file__).resolve().parent
# Explicit opt-in; defaults preserve the active v1.10 file layout.
# Set STOCKTRACKER_RUNTIME_ROOT to a folder OUTSIDE the Git checkout.
_runtime_setting = os.getenv("STOCKTRACKER_RUNTIME_ROOT", "").strip()
RUNTIME_ROOT = Path(_runtime_setting).expanduser().resolve() if _runtime_setting else ROOT
if _runtime_setting and (RUNTIME_ROOT == ROOT or ROOT in RUNTIME_ROOT.parents):
    raise ValueError("STOCKTRACKER_RUNTIME_ROOT must be outside the source repository")

MARKET_TZ = ZoneInfo("America/New_York")
EVIDENCE_ROOT = RUNTIME_ROOT / "analysis" / "evidence"
DAILY_ROOT = RUNTIME_ROOT / "analysis" / "daily"

load_dotenv(ROOT / ".env.config")
load_dotenv(ROOT / ".env", override=True)


def project_path(env_name: str, default_name: str) -> Path:
    raw = str(os.getenv(env_name) or "").strip()
    path = Path(raw).expanduser() if raw else ROOT / default_name
    return path if path.is_absolute() else ROOT / path


DB_PATH = project_path("MULTI_DB_PATH", "momentum_trader.sqlite3")
STATE_PATH = project_path("DASHBOARD_STATE_PATH", "dashboard_state.json")
GEO_FEED_PATH = project_path("GEO_FEED_PATH", "geo_feed.json")
GEO_LOG_PATH = project_path("GEO_LOG_PATH", "geo_feed.log")

TABLE_QUERIES = {
    "decisions": ("ts", "SELECT * FROM decisions WHERE ts>=? AND ts<? ORDER BY ts"),
    "orders": ("ts", "SELECT * FROM orders WHERE ts>=? AND ts<? ORDER BY ts"),
    "fills": ("ts", "SELECT * FROM fills WHERE ts>=? AND ts<? ORDER BY ts"),
    "realized": ("ts", "SELECT * FROM realized WHERE ts>=? AND ts<? ORDER BY ts"),
    "decision_funnel": ("ts", "SELECT * FROM decision_funnel WHERE ts>=? AND ts<? ORDER BY ts"),
    "order_attempts": ("ts", "SELECT * FROM order_attempts WHERE ts>=? AND ts<? ORDER BY ts"),
    "market_regime_shadow": ("ts", "SELECT * FROM market_regime_shadow WHERE ts>=? AND ts<? ORDER BY ts"),
    "regime_decision_shadow": ("ts", "SELECT * FROM regime_decision_shadow WHERE ts>=? AND ts<? ORDER BY ts"),
    "financial_leverage_shadow": ("ts", "SELECT * FROM financial_leverage_shadow WHERE ts>=? AND ts<? ORDER BY ts"),
    "financial_leverage_signals": ("ts", "SELECT * FROM financial_leverage_signals WHERE ts>=? AND ts<? ORDER BY ts"),
    "financial_leverage_outcomes": ("observed_at", "SELECT * FROM financial_leverage_outcomes WHERE observed_at>=? AND observed_at<? ORDER BY observed_at"),
    "premarket_intelligence": ("ts", "SELECT * FROM premarket_intelligence WHERE ts>=? AND ts<? ORDER BY ts"),
    "zpta_observations": ("ts", "SELECT * FROM zpta_observations WHERE ts>=? AND ts<? ORDER BY ts"),
    "zpta_predictions": ("created_ts", "SELECT * FROM zpta_predictions WHERE created_ts>=? AND created_ts<? ORDER BY created_ts"),
    "zpta_shadow_trades": ("entry_ts", "SELECT * FROM zpta_shadow_trades WHERE entry_ts>=? AND entry_ts<? ORDER BY entry_ts"),
}

SENSITIVE_KEY = re.compile(r"(?i)(api.?key|secret|password|authorization|access.?token|refresh.?token)")
LOG_SECRET = re.compile(
    r"(?i)((?:api.?key|secret|password|authorization|access.?token|refresh.?token)\s*[=:]\s*)\S+"
)


def day_bounds(date_text: str) -> tuple[str, str]:
    day = datetime.fromisoformat(date_text).date()
    start = datetime.combine(day, dtime.min, tzinfo=MARKET_TZ)
    return start.astimezone(timezone.utc).isoformat(), (start + timedelta(days=1)).astimezone(timezone.utc).isoformat()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return bool(row)


def hash_identifier(value: Any) -> str:
    return "sha256:" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]


def sanitize_mapping(row: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in row.items():
        if SENSITIVE_KEY.search(str(key)):
            clean[key] = "[REDACTED]" if value not in (None, "") else value
        elif key == "alpaca_order_id" and value not in (None, ""):
            clean[key] = hash_identifier(value)
        else:
            clean[key] = value
    return clean


def sanitize_object(value: Any) -> Any:
    if isinstance(value, dict):
        return sanitize_mapping({k: sanitize_object(v) for k, v in value.items()})
    if isinstance(value, list):
        return [sanitize_object(x) for x in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(sanitize_object(value), indent=2, default=str), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not fields:
            return
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(sanitize_mapping(row))


def file_metadata(path: Path, rows: int | None = None, first_ts: Any = None, last_ts: Any = None) -> dict[str, Any]:
    raw = path.read_bytes()
    result: dict[str, Any] = {
        "path": str(path.relative_to(RUNTIME_ROOT)).replace("\\", "/"),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    if rows is not None:
        result.update({"rows": rows, "first_ts": first_ts, "last_ts": last_ts})
    return result


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def integrity_analysis(tables: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    funnel = tables.get("decision_funnel", [])
    attempts = tables.get("order_attempts", [])
    fills = tables.get("fills", [])
    predictions = tables.get("zpta_predictions", [])

    event_ids = [str(x.get("event_id") or "") for x in funnel if x.get("event_id")]
    event_set = set(event_ids)
    attempt_links = [str(x.get("decision_event_id") or "") for x in attempts if x.get("decision_event_id")]
    orphan_attempts = [x for x in attempt_links if x not in event_set]
    accepted_missing_id = [
        x for x in attempts
        if int(float(x.get("accepted") or 0)) > 0 and not x.get("alpaca_order_id")
    ]
    resolved_missing_return = [
        x for x in predictions
        if x.get("resolved_ts") not in (None, "") and x.get("forward_return") in (None, "")
    ]
    fill_keys = [str(x.get("alpaca_order_id") or "") for x in fills if x.get("alpaca_order_id")]

    issues = []
    if len(event_ids) != len(event_set):
        issues.append("DUPLICATE_DECISION_EVENT_IDS")
    if orphan_attempts:
        issues.append("ORPHAN_ORDER_ATTEMPTS")
    if accepted_missing_id:
        issues.append("ACCEPTED_ATTEMPTS_WITHOUT_ORDER_ID")
    if len(fill_keys) != len(set(fill_keys)):
        issues.append("DUPLICATE_FILL_ORDER_IDS")
    if resolved_missing_return:
        issues.append("RESOLVED_ZPTA_PREDICTIONS_WITHOUT_RETURN")

    gates = Counter(str(x.get("gate_reason") or "UNKNOWN") for x in attempts)
    exit_reasons = Counter(str(x.get("exit_reason") or "UNKNOWN") for x in tables.get("zpta_shadow_trades", []))
    return {
        "status": "PASS" if not issues else "WARN",
        "issues": issues,
        "all_published_rows_analyzed": sum(len(v) for v in tables.values()),
        "table_count": len(tables),
        "duplicate_decision_event_ids": len(event_ids) - len(event_set),
        "orphan_order_attempts": len(orphan_attempts),
        "accepted_attempts_without_order_id": len(accepted_missing_id),
        "duplicate_fill_order_ids": len(fill_keys) - len(set(fill_keys)),
        "resolved_zpta_predictions_without_return": len(resolved_missing_return),
        "order_gate_counts": dict(gates),
        "zpta_exit_reason_counts": dict(exit_reasons),
    }


def export(date_text: str) -> tuple[dict[str, Any], Path]:
    start_utc, end_utc = day_bounds(date_text)
    out_dir = EVIDENCE_ROOT / date_text
    out_dir.mkdir(parents=True, exist_ok=True)

    tables: dict[str, list[dict[str, Any]]] = {}
    db_error = None
    if DB_PATH.exists():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                for name, (_, query) in TABLE_QUERIES.items():
                    if table_exists(conn, name):
                        tables[name] = [dict(row) for row in conn.execute(query, (start_utc, end_utc))]
                    else:
                        tables[name] = []
        except Exception as exc:
            db_error = str(exc)
    else:
        db_error = f"Database missing: {DB_PATH}"
        tables = {name: [] for name in TABLE_QUERIES}

    files = []
    for name, (time_field, _) in TABLE_QUERIES.items():
        rows = tables.get(name, [])
        path = out_dir / f"{name}.csv"
        write_csv(path, rows)
        stamps = [row.get(time_field) for row in rows if row.get(time_field)]
        files.append(file_metadata(path, len(rows), stamps[0] if stamps else None, stamps[-1] if stamps else None))

    snapshots = {
        "dashboard_state.json": read_json(STATE_PATH),
        "geo_feed.json": read_json(GEO_FEED_PATH),
    }
    for filename, payload in snapshots.items():
        path = out_dir / filename
        write_json(path, payload or {})
        files.append(file_metadata(path))

    geo_tail = out_dir / "geo_feed_tail.txt"
    if GEO_LOG_PATH.exists():
        lines = GEO_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]
        geo_tail.write_text("\n".join(LOG_SECRET.sub(r"\1[REDACTED]", x) for x in lines) + "\n", encoding="utf-8")
    else:
        geo_tail.write_text("", encoding="utf-8")
    files.append(file_metadata(geo_tail))

    analysis = integrity_analysis(tables)
    analysis["database_error"] = db_error
    analysis["empty_tables"] = [name for name, rows in tables.items() if not rows]
    analysis_path = out_dir / "integrity_analysis.json"
    write_json(analysis_path, analysis)
    files.append(file_metadata(analysis_path))

    manifest = {
        "schema_version": 1,
        "review_date": date_text,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sanitized": True,
        "paper_only": True,
        "market_timezone": str(MARKET_TZ),
        "date_window_utc": {"start": start_utc, "end": end_utc},
        "source_database_present": DB_PATH.exists(),
        "database_error": db_error,
        "files": files,
        "integrity_analysis": analysis,
    }
    manifest_path = out_dir / "manifest.json"
    write_json(manifest_path, manifest)

    performance_input = DAILY_ROOT / date_text / "performance_input.json"
    bundle = read_json(performance_input)
    if isinstance(bundle, dict):
        bundle["supporting_logs"] = {
            "manifest_path": str(manifest_path.relative_to(RUNTIME_ROOT)).replace("\\", "/"),
            "published_file_count": len(files) + 1,
            "published_row_count": analysis["all_published_rows_analyzed"],
            "files": files,
        }
        bundle["supporting_log_analysis"] = analysis
        performance_input.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    return manifest, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(MARKET_TZ).date().isoformat())
    args = parser.parse_args()
    manifest, path = export(args.date)
    analysis = manifest["integrity_analysis"]
    print(f"Published supporting evidence manifest: {path}")
    print(
        f"Files: {len(manifest['files']) + 1} | Rows analyzed: "
        f"{analysis['all_published_rows_analyzed']} | Integrity: {analysis['status']}"
    )


if __name__ == "__main__":
    main()
