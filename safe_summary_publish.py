#!/usr/bin/env python3
"""Fail-closed, allowlisted DAILY SUMMARY bridge for isolated StockTracker runtime.

Publishes only compact numeric/enum paper-trading metrics into the PRIVATE
repository when an external STOCKTRACKER_RUNTIME_ROOT is configured. Never
publishes positions, order IDs, raw events, logs, provider error details,
prompts, API keys or the full AI proposal text. No brokerage/API calls.
Preserves the separate confidential runtime research storage.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATE_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")
SUMMARY_REL = Path("analysis/performance/sanitized_latest.json")
DAILY_REL = Path("analysis/performance/sanitized_daily")


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    # JSON dump rejects NaN/Inf. Exclude outliers caused by corrupt fields.
    from math import isfinite
    return round(float(value), 4) if isfinite(value) else None


def _count(value):
    return int(value) if type(value) is int and 0 <= value <= 100000000 else None


def summary_from(report, current=None):
    if not isinstance(report, dict):
        raise ValueError("Report must be an object")
    metrics = report.get("metrics")
    review = report.get("review")
    if not isinstance(metrics, dict) or not isinstance(review, dict):
        raise ValueError("Missing metrics/review")
    day = metrics.get("review_date")
    if not isinstance(day, str) or not DATE_RE.fullmatch(day) or date.fromisoformat(day).isoformat() != day:
        raise ValueError("Invalid review date")
    if review.get("review_date") != day or metrics.get("paper_only") is not True:
        raise ValueError("Review date or paper-only invariant mismatch")
    realized = metrics.get("realized") or {}
    orders = metrics.get("orders") or {}
    decisions = metrics.get("decisions") or {}
    inputs = metrics.get("coverage") or {}
    zpta = metrics.get("zpta_shadow") or {}
    fin = metrics.get("financial_leverage_shadow") or {}
    if not all(isinstance(x, dict) for x in (realized, orders, decisions, inputs, zpta, fin)):
        raise ValueError("Unexpected metrics structure")

    quality = review.get("data_quality")
    if quality not in ("GOOD", "LIMITED", "INSUFFICIENT"):
        quality = "UNKNOWN"
    source = review.get("review_source")
    if source not in ("OPENAI", "DETERMINISTIC_FALLBACK"):
        source = "UNKNOWN"

    proposals = []
    if isinstance(current, dict) and current.get("review_date") == day:
        for item in current.get("proposals") or []:
            if not isinstance(item, dict):
                continue
            proposal_id = item.get("proposal_id")
            status = item.get("status")
            if not isinstance(proposal_id, str) or not re.fullmatch(r"P-STOCK-\d{8}-\d{2}", proposal_id):
                continue
            if status not in {"PENDING", "APPROVED", "DECLINED", "IMPLEMENTING", "TESTING",
                              "READY_TO_DEPLOY", "DEPLOYED", "FAILED", "ROLLED_BACK", "SHADOW", "BUNDLED"}:
                status = "UNKNOWN"
            proposals.append({"id": proposal_id, "status": status})

    # Historical reports lack daily starting/ending equity. Realized P/L is
    # not portfolio return, and should never be converted using exposure.
    return {
        "schema": "stocktracker_sanitized_summary_v1",
        "review_date": day,
        "paper_only": True,
        "quality": quality,
        "review_source": source,
        "coverage": {
            "database_available": bool(inputs.get("db_path_exists")) and not bool(inputs.get("db_error")),
            "dashboard_snapshot_available": bool(inputs.get("dashboard_state_exists")),
        },
        "daily": {
            "decision_rows": _count(decisions.get("rows")),
            "order_rows": _count(orders.get("rows")),
            "buy_orders": _count(orders.get("buys")),
            "sell_orders": _count(orders.get("sells")),
            "closed_trades": _count(realized.get("rows")),
            "realized_pnl_usd": _number(realized.get("realized_pnl")),
            "wins": _count(realized.get("wins")),
            "losses": _count(realized.get("losses")),
            "win_rate_pct": _number(realized.get("win_rate_pct")),
        },
        "shadow": {
            "zpta_resolved_predictions": _count(zpta.get("resolved_predictions")),
            "zpta_shadow_trades": _count(zpta.get("shadow_trades")),
            "financial_leverage_signal_rows": _count(fin.get("signal_rows")),
        },
        "one_percent_goal": {
            "daily_target_pct": 1.0,
            "daily_portfolio_return_pct": None,
            "since_inception_return_pct": None,
            "daily_goal_met": None,
            "status": "NOT_MEASURABLE_NO_VERIFIED_START_END_EQUITY",
        },
        "proposal_ids": proposals,
    }


def read_json(path):
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("Expected JSON object")
    return obj


def git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("Git operation failed (details withheld; see local diagnostics)")
    return result.stdout.strip()


def validate_git_safe(day):
    if git("branch", "--show-current") != "main":
        raise RuntimeError("Summary publication requires main")
    if git("diff", "--cached", "--name-only"):
        raise RuntimeError("Preexisting staged changes; refusing summary publication")
    allowed = {SUMMARY_REL.as_posix(), (DAILY_REL / (day + ".json")).as_posix()}
    for row in git("status", "--porcelain", "--untracked-files=all").splitlines():
        path = row[3:].strip().strip('"').replace("\\", "/")
        if path not in allowed:
            raise RuntimeError("Unrelated worktree changes; refusing summary publication")


def publish(runtime_root, *, commit=True):
    runtime_root = runtime_root.expanduser().resolve()
    if runtime_root == ROOT or ROOT in runtime_root.parents:
        raise ValueError("Runtime root must be outside Git checkout")
    report = read_json(runtime_root / "analysis/performance/latest.json")
    date_text = str(report.get("metrics", {}).get("review_date") or "")
    proposal_path = runtime_root / "analysis/proposals/current.json"
    current = read_json(proposal_path) if proposal_path.is_file() else None
    data = summary_from(report, current)
    target = ROOT / SUMMARY_REL
    daily = ROOT / DAILY_REL / (date_text + ".json")
    # Protect from a stale catch-up job overwriting a newer summary.
    if target.is_file():
        existing = read_json(target)
        if existing.get("schema") == "stocktracker_sanitized_summary_v1" and str(existing.get("review_date", "")) > date_text:
            raise RuntimeError("Refusing to replace a newer published review")
    if commit:
        validate_git_safe(date_text)
    content = json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    daily.parent.mkdir(parents=True, exist_ok=True)
    daily.write_text(content, encoding="utf-8")
    target.write_text(content, encoding="utf-8")
    if commit:
        git("add", "--", SUMMARY_REL.as_posix(), (DAILY_REL / (date_text + ".json")).as_posix())
        allowed = {SUMMARY_REL.as_posix(), (DAILY_REL / (date_text + ".json")).as_posix()}
        staged = set(git("diff", "--cached", "--name-only").splitlines())
        if not staged.issubset(allowed):
            raise RuntimeError("Staged changes outside summary allowlist")
        if staged:
            git("commit", "-m", "Publish allowlisted StockTracker paper summary " + date_text)
            # Never run git pull, force push, rebase, or reset from the review.
            git("push", "origin", "HEAD:main")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path,
                        default=Path(os.getenv("STOCKTRACKER_RUNTIME_ROOT", "")))
    parser.add_argument("--no-push", action="store_true",
                        help="Build allowlisted files locally without a Git commit/push")
    args = parser.parse_args()
    if not os.getenv("STOCKTRACKER_RUNTIME_ROOT", "").strip() and not parser.get_default("runtime_root"):
        parser.error("STOCKTRACKER_RUNTIME_ROOT is required")
    try:
        result = publish(args.runtime_root, commit=not args.no_push)
    except Exception as exc:
        # Don't echo provider, runtime, local-path, or Git exception details.
        print("STOCKTRACKER_SANITIZED_SUMMARY_FAILED: " + type(exc).__name__)
        raise SystemExit(1)
    print("STOCKTRACKER_SANITIZED_SUMMARY_OK: " + result["review_date"])


if __name__ == "__main__":
    main()
