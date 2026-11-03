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

from infrastructure.invested_capital_audit import SAFE_BROKER_BLOCKER_CODES

ROOT = Path(__file__).resolve().parent
DATE_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")
SUMMARY_REL = Path("analysis/performance/sanitized_latest.json")
DAILY_REL = Path("analysis/performance/sanitized_daily")


def pushover_api_accepted(response):
    """True only for an observed HTTP 200 and Pushover JSON status=1.

    Provider acceptance is not device delivery. Never persist response bodies,
    message IDs, tokens, or provider exception text.
    """
    if getattr(response, "status_code", None) != 200:
        return False
    try:
        body = response.json()
    except (ValueError, TypeError):
        return False
    return isinstance(body, dict) and type(body.get("status")) is int and body["status"] == 1



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

    # Only a dated read-only PAPER account observation is eligible for the
    # separate account-change metric. This is not return on deployed capital
    # and is not cash-flow-adjusted portfolio ROI.
    portfolio = metrics.get("portfolio_performance") or {}
    if not isinstance(portfolio, dict):
        raise ValueError("Invalid paper account metrics")
    account_eligible = (
        portfolio.get("review_date") == day
        and portfolio.get("source") == "ALPACA_PAPER_ACCOUNT"
        and portfolio.get("status") == "PAPER_ACCOUNT_CHANGE_UNADJUSTED_CASH_FLOWS"
        and portfolio.get("cash_flows_reconciled") is False
        and portfolio.get("full_portfolio_return_verified") is False
    )
    account_day_pct = _number(portfolio.get("daily_account_change_pct")) if account_eligible else None
    observed_change = _number(portfolio.get("observed_window_account_change_pct")) if account_eligible else None
    observed_drawdown = _number(portfolio.get("observed_window_max_drawdown_pct")) if account_eligible else None
    observed_sessions = _count(portfolio.get("observed_session_count")) if account_eligible else None
    # Two different percentages:
    # (1) realized closed-lot return on sold cost basis, from a reconciled
    #     but locally observed-only PAPER fills ledger;
    # (2) MODELED total PAPER account P/L divided by *peak capital deployed*
    #     at recorded cost, only after broker account/positions/orders/equity
    #     history and zero reported cashflows cross-reconcile.
    # No unverified positions, order IDs or broker account ID are published.
    invested = metrics.get("invested_capital") or {}
    if not isinstance(invested, dict):
        raise ValueError("Unexpected invested-capital metric")
    local_ok = (
        invested.get("review_date") == day
        and invested.get("source") == "LOCAL_PAPER_FILLED_ORDERS_MOVING_AVERAGE"
        and invested.get("status") == "LOCAL_CLOSED_FILLS_RECONCILED_NOT_BROKER_ATTESTED"
    )
    broker_ok = (
        local_ok and account_eligible
        and invested.get("broker_reconciled") is True
        and invested.get("cash_flows_reconciled") is True
        and invested.get("daily_invested_capital_return_status")
            == "MODELED_PAPER_RETURN_ON_PEAK_DEPLOYED_COST"
    )
    closed_pct = _number(invested.get("daily_closed_invested_capital_return_pct")) if local_ok else None
    observed_pct = _number(invested.get("observed_fills_closed_invested_return_pct")) if local_ok else None
    daily_capital_roi = _number(invested.get("daily_invested_capital_return_pct")) if broker_ok else None
    # Account equity day change and invested-capital ROI have different
    # denominators. Never use the former to grade the user's 1%-on-invested
    # goal. True cash-flow-adjusted portfolio ROI remains unverified.
    broker_ok = broker_ok and daily_capital_roi is not None and account_day_pct is not None
    if not broker_ok:
        daily_capital_roi = None
    # Historical paper-account curve uses the broker's fully dated daily
    # history, independent full filled-order set and exchange-session coverage.
    # "Since first recorded fill" is NOT the same as proven project inception.
    observed_history = (
        broker_ok
        and invested.get("inception_basis_status") in {
            "OBSERVED_FIRST_FILL_ONLY",
            "CONFIGURED_START_EQUALS_FIRST_FILL_WITH_BROKER_COVERAGE",
        }
        and _count(invested.get("since_first_recorded_fill_sessions")) is not None
        and _count(invested.get("since_first_recorded_fill_sessions")) > 0
    )
    observed_history_return = (
        _number(invested.get("since_first_recorded_fill_portfolio_return_pct"))
        if observed_history else None
    )
    observed_history_drawdown = (
        _number(invested.get("since_first_recorded_fill_portfolio_drawdown_pct"))
        if observed_history else None
    )
    inception_eligible = (
        observed_history and observed_history_return is not None
        and observed_history_drawdown is not None
        and invested.get("inception_basis_status")
            == "CONFIGURED_START_EQUALS_FIRST_FILL_WITH_BROKER_COVERAGE"
    )
    # The Pushover HTTP+JSON acknowledgement is a separate, dated host fact.
    # A completed EOD review does not imply a notification was accepted.
    notification = metrics.get("eod_notification") or {}
    if not isinstance(notification, dict):
        raise ValueError("Unexpected EOD notification metadata")
    notice = notification.get("provider_status") if notification.get("review_date") == day else None
    if notice not in {"API_ACCEPTED", "API_NOT_ACCEPTED", "UNCONFIRMED",
                      "DISABLED", "CONFIG_MISSING"}:
        notice = "UNVERIFIED"
    # Never label a gross account-equity change as an invested-capital return.
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
        "eod_notification": {
            "provider_status": notice,
            "provider_accepted": notice == "API_ACCEPTED",
            "device_delivery_verified": False,
        },
        "paper_account_observation": {
            "status": "PAPER_ACCOUNT_CHANGE_UNADJUSTED_CASH_FLOWS" if account_eligible else "MISSING",
            "daily_account_change_pct": account_day_pct,
            "observed_window_account_change_pct": observed_change,
            "observed_window_max_drawdown_pct": observed_drawdown,
            "observed_session_count": observed_sessions,
            "cash_flows_reconciled": False,
            "invested_capital_daily_return_pct": None,
            "inception_portfolio_return_pct": None,
            "source": "ALPACA_PAPER_ACCOUNT" if account_eligible else "UNVERIFIED",
        },
        "invested_capital": {
            "status": (
                "MODELED_PAPER_BROKER_AND_LEDGER_RECONCILED" if broker_ok
                else "MODELED_LOCAL_CLOSED_LOTS_ONLY" if local_ok else "MISSING"
            ),
            "broker_reconciliation_blocker": (
                "NONE" if broker_ok
                else invested.get("broker_reconciliation_blocker")
                if local_ok and invested.get("broker_reconciliation_blocker") in SAFE_BROKER_BLOCKER_CODES
                else "UNVERIFIED"
            ),
            "daily_closed_lot_realized_return_pct": closed_pct,
            "daily_closed_lot_cost_basis_usd": (
                _number(invested.get("daily_closed_cost_basis_usd")) if local_ok else None
            ),
            "since_first_observed_fill_closed_lot_return_pct": observed_pct,
            "first_observed_fill_date": (
                invested.get("first_observed_fill_date") if local_ok and
                isinstance(invested.get("first_observed_fill_date"), str) and
                DATE_RE.fullmatch(invested["first_observed_fill_date"]) else None
            ),
            "daily_peak_deployed_cost_basis_usd": (
                _number(invested.get("peak_session_deployed_cost_usd")) if broker_ok else None
            ),
            "daily_portfolio_return_on_peak_deployed_capital_pct": daily_capital_roi,
            "daily_one_percent_invested_goal_met": (
                daily_capital_roi >= 1.0 if broker_ok else None
            ),
            "since_first_observed_fill_portfolio_return_pct": observed_history_return,
            "since_first_observed_fill_portfolio_drawdown_pct": observed_history_drawdown,
            "since_first_observed_fill_sessions": (
                _count(invested.get("since_first_recorded_fill_sessions"))
                if observed_history else None
            ),
            "since_inception_invested_return_pct": (
                observed_history_return if inception_eligible else None
            ),
            "since_inception_invested_drawdown_pct": (
                observed_history_drawdown if inception_eligible else None
            ),
            "inception_evidence_status": (
                "INCEPTION_DATE_CONFIRMED_MODELED_PAPER" if inception_eligible
                else "OBSERVED_FIRST_FILL_NOT_PROVEN_INCEPTION" if observed_history
                else "MISSING"
            ),
            "calculation": "DAILY_NET_ACCOUNT_PNL_DIVIDED_BY_PEAK_FILLED_COST_BASIS"
                           if broker_ok else "CLOSED_LOT_PNL_DIVIDED_BY_CLOSED_LOT_COST"
                           if local_ok else "MISSING",
            "classification": "MODELED_PAPER" if broker_ok or local_ok else "MISSING",
        },
        "one_percent_goal": {
            "daily_target_pct": 1.0,
            # No true cash-flow-adjusted whole-account portfolio return here.
            "daily_portfolio_return_pct": None,
            # Explicit denominator for the requested deployed-capital goal.
            "daily_invested_capital_return_pct": daily_capital_roi,
            "return_basis": "MODELED_PAPER_PEAK_DEPLOYED_FILLED_COST"
                            if broker_ok else "MISSING",
            "since_inception_return_pct": None,
            "daily_goal_met": daily_capital_roi >= 1.0 if broker_ok else None,
            "status": "MODELED_PAPER_BROKER_CASHFLOW_ZERO_RECONCILED"
                      if broker_ok else "NOT_MEASURABLE_NO_VERIFIED_INVESTED_CAPITAL_RETURN",
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
