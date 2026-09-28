#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env.config")
load_dotenv(ROOT / ".env", override=True)

MARKET_TZ = ZoneInfo("America/New_York")
DAILY_DIR = ROOT / "analysis" / "daily"
PERF_DIR = ROOT / "analysis" / "performance"

def project_path(env_name: str, default_name: str) -> Path:
    raw = str(os.getenv(env_name) or "").strip()
    p = Path(raw).expanduser() if raw else ROOT / default_name
    return p if p.is_absolute() else ROOT / p

DB_PATH = project_path("MULTI_DB_PATH", "momentum_trader.sqlite3")
LOG_ROOT = project_path("MULTI_LOG_ROOT", "momentum_logs")
STATE_PATH = project_path("DASHBOARD_STATE_PATH", "dashboard_state.json")
GEO_FEED_PATH = project_path("GEO_FEED_PATH", "geo_feed.json")
GEO_LOG_PATH = project_path("GEO_LOG_PATH", "geo_feed.log")

def fnum(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

def safe_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def day_bounds(date_text: str):
    d = datetime.fromisoformat(date_text).date()
    start_local = datetime.combine(d, dtime.min, tzinfo=MARKET_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc).isoformat(), end_local.astimezone(timezone.utc).isoformat()

def rows(conn, sql, params=()):
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    except Exception:
        return []

def summarize_decisions(items):
    by_symbol = defaultdict(list)
    actions = Counter()
    for r in items:
        by_symbol[str(r.get("symbol") or "?")].append(r)
        actions[str(r.get("decision") or "UNKNOWN").upper()] += 1

    out = {}
    for sym, group in sorted(by_symbol.items()):
        scores = [fnum(x.get("score")) for x in group]
        tech = [fnum(x.get("technical")) for x in group]
        ctx = [fnum(x.get("context")) for x in group]
        vix = [fnum(x.get("vix_adjustment")) for x in group]
        geo = [fnum(x.get("geo_adjustment")) for x in group]
        acts = Counter(str(x.get("decision") or "UNKNOWN").upper() for x in group)
        out[sym] = {
            "rows": len(group),
            "buy": acts.get("BUY", 0),
            "sell": acts.get("SELL", 0),
            "hold": acts.get("HOLD", 0),
            "avg_score": round(sum(scores) / len(scores), 3) if scores else None,
            "median_score": round(median(scores), 3) if scores else None,
            "max_score": round(max(scores), 3) if scores else None,
            "min_score": round(min(scores), 3) if scores else None,
            "avg_technical": round(sum(tech) / len(tech), 3) if tech else None,
            "avg_context": round(sum(ctx) / len(ctx), 3) if ctx else None,
            "avg_vix_adjustment": round(sum(vix) / len(vix), 3) if vix else None,
            "avg_geo_adjustment": round(sum(geo) / len(geo), 3) if geo else None,
        }
    return {"rows": len(items), "actions": dict(actions), "by_symbol": out}

def summarize_orders(items):
    by_symbol = defaultdict(lambda: {"buy": 0, "sell": 0, "buy_notional": 0.0, "sell_notional": 0.0})
    for r in items:
        sym = str(r.get("symbol") or "?")
        side = str(r.get("side") or "").lower()
        notional = abs(fnum(r.get("notional")))
        if side in {"buy", "sell"}:
            by_symbol[sym][side] += 1
            by_symbol[sym][f"{side}_notional"] += notional
    return {
        "rows": len(items),
        "buys": sum(v["buy"] for v in by_symbol.values()),
        "sells": sum(v["sell"] for v in by_symbol.values()),
        "by_symbol": {k: {kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in sorted(by_symbol.items())},
    }


def summarize_funnel(items):
    gates = Counter(str(r.get("gate_reason") or "UNKNOWN") for r in items)
    dispositions = Counter(str(r.get("final_disposition") or "UNKNOWN") for r in items)
    sides = Counter(str(r.get("side") or "UNKNOWN") for r in items)
    return {
        "rows": len(items),
        "raw_threshold_crossings": sum(int(fnum(r.get("raw_threshold_cross")) > 0) for r in items),
        "by_side": dict(sides),
        "by_gate_reason": dict(gates),
        "by_final_disposition": dict(dispositions),
    }


def summarize_order_attempts(items):
    attempted = sum(int(fnum(r.get("attempted")) > 0) for r in items)
    accepted = sum(int(fnum(r.get("accepted")) > 0) for r in items)
    gates = Counter(str(r.get("gate_reason") or "UNKNOWN") for r in items)
    return {
        "rows": len(items),
        "attempted": attempted,
        "accepted": accepted,
        "blocked_before_submit": len(items) - attempted,
        "submit_failures": max(0, attempted - accepted),
        "by_gate_reason": dict(gates),
    }

def summarize_realized(items):
    by_symbol = defaultdict(list)
    for r in items:
        by_symbol[str(r.get("symbol") or "?")].append(fnum(r.get("pnl")))
    vals = [fnum(r.get("pnl")) for r in items]
    wins = [x for x in vals if x > 0]
    losses = [x for x in vals if x < 0]
    return {
        "rows": len(items),
        "realized_pnl": round(sum(vals), 2),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(vals) * 100.0, 2) if vals else None,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "best_trade": round(max(vals), 2) if vals else None,
        "worst_trade": round(min(vals), 2) if vals else None,
        "by_symbol": {k: {"trades": len(v), "pnl": round(sum(v), 2)} for k, v in sorted(by_symbol.items())},
    }

def summarize_daily_csv(date_text: str):
    folder = LOG_ROOT / date_text
    out = {"folder_exists": folder.exists(), "decision_rows": 0, "trade_rows": 0}
    for name, key in (("decisions.csv", "decision_rows"), ("trades.csv", "trade_rows")):
        path = folder / name
        if path.exists():
            try:
                with path.open("r", newline="", encoding="utf-8") as f:
                    out[key] = sum(1 for _ in csv.DictReader(f))
            except Exception:
                pass
    return out

def geo_log_health():
    if not GEO_LOG_PATH.exists():
        return {"exists": False}
    try:
        lines = GEO_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]
    except Exception:
        return {"exists": True, "read_error": True}
    lowered = [x.lower() for x in lines]
    return {
        "exists": True,
        "tail_lines": len(lines),
        "error_lines": sum("error" in x or "failed" in x or "exception" in x for x in lowered),
        "warning_lines": sum("warning" in x for x in lowered),
        "last_line": lines[-1][-300:] if lines else "",
    }


def table_exists(conn, name):
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def summarize_market_regime(items):
    states = Counter(str(r.get("regime_state") or "UNKNOWN") for r in items)
    scores = [fnum(r.get("regime_score")) for r in items if r.get("regime_score") is not None]
    latest = items[-1] if items else {}
    return {
        "rows": len(items),
        "state_counts": dict(states),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
        "latest_state": latest.get("regime_state"),
        "latest_score": latest.get("regime_score"),
        "latest_defensive_asset": latest.get("defensive_asset"),
    }


def summarize_regime_decisions(items):
    actions = Counter(str(r.get("shadow_action") or "UNKNOWN") for r in items)
    states = Counter(str(r.get("regime_state") or "UNKNOWN") for r in items)
    symbols = Counter(str(r.get("symbol") or "?") for r in items)
    return {
        "rows": len(items),
        "by_shadow_action": dict(actions),
        "by_regime_state": dict(states),
        "by_symbol": dict(symbols),
    }


def summarize_financial_leverage(snapshots, signals, outcomes):
    candidate_snapshots = Counter(str(r.get("candidate") or "NONE") for r in snapshots)
    signal_counts = Counter(str(r.get("candidate") or "UNKNOWN") for r in signals)
    grouped = defaultdict(list)
    for r in outcomes:
        key = (str(r.get("candidate") or "UNKNOWN"), int(fnum(r.get("horizon_minutes"))))
        grouped[key].append(fnum(r.get("candidate_return")))

    outcome_summary = {}
    for (candidate, horizon), vals in sorted(grouped.items()):
        key = f"{candidate}_{horizon}m"
        outcome_summary[key] = {
            "n": len(vals),
            "avg_return_pct": round(sum(vals) / len(vals) * 100.0, 3) if vals else None,
            "median_return_pct": round(median(vals) * 100.0, 3) if vals else None,
            "win_rate_pct": round(sum(v > 0 for v in vals) / len(vals) * 100.0, 2) if vals else None,
            "best_return_pct": round(max(vals) * 100.0, 3) if vals else None,
            "worst_return_pct": round(min(vals) * 100.0, 3) if vals else None,
        }

    latest = snapshots[-1] if snapshots else {}
    return {
        "snapshot_rows": len(snapshots),
        "candidate_snapshot_counts": dict(candidate_snapshots),
        "signal_rows": len(signals),
        "signal_counts": dict(signal_counts),
        "outcome_rows": len(outcomes),
        "outcomes": outcome_summary,
        "latest_candidate": latest.get("candidate"),
        "latest_candidate_score": latest.get("candidate_score"),
        "latest_regime_state": latest.get("regime_state"),
    }

def build(date_text: str):
    start_utc, end_utc = day_bounds(date_text)
    decisions = []
    orders = []
    realized = []
    fills = []
    funnel = []
    order_attempts = []
    regime_rows = []
    regime_decisions = []
    fin_rows = []
    fin_signals = []
    fin_outcomes = []
    db_error = None
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            decisions = rows(conn, "SELECT * FROM decisions WHERE ts>=? AND ts<? ORDER BY ts", (start_utc, end_utc))
            orders = rows(conn, "SELECT * FROM orders WHERE ts>=? AND ts<? ORDER BY ts", (start_utc, end_utc))
            realized = rows(conn, "SELECT * FROM realized WHERE ts>=? AND ts<? ORDER BY ts", (start_utc, end_utc))
            fills = rows(conn, "SELECT * FROM fills WHERE ts>=? AND ts<? ORDER BY ts", (start_utc, end_utc))
            if table_exists(conn, "decision_funnel"):
                funnel = rows(conn, "SELECT * FROM decision_funnel WHERE ts>=? AND ts<? ORDER BY ts", (start_utc, end_utc))
            if table_exists(conn, "order_attempts"):
                order_attempts = rows(conn, "SELECT * FROM order_attempts WHERE ts>=? AND ts<? ORDER BY ts", (start_utc, end_utc))
            if table_exists(conn, "market_regime_shadow"):
                regime_rows = rows(conn, "SELECT * FROM market_regime_shadow WHERE ts>=? AND ts<? ORDER BY ts", (start_utc, end_utc))
            if table_exists(conn, "regime_decision_shadow"):
                regime_decisions = rows(conn, "SELECT * FROM regime_decision_shadow WHERE ts>=? AND ts<? ORDER BY ts", (start_utc, end_utc))
            if table_exists(conn, "financial_leverage_shadow"):
                fin_rows = rows(conn, "SELECT * FROM financial_leverage_shadow WHERE ts>=? AND ts<? ORDER BY ts", (start_utc, end_utc))
            if table_exists(conn, "financial_leverage_signals"):
                fin_signals = rows(conn, "SELECT * FROM financial_leverage_signals WHERE ts>=? AND ts<? ORDER BY ts", (start_utc, end_utc))
            if table_exists(conn, "financial_leverage_outcomes"):
                fin_outcomes = rows(conn, "SELECT * FROM financial_leverage_outcomes WHERE observed_at>=? AND observed_at<? ORDER BY observed_at", (start_utc, end_utc))
            conn.close()
        except Exception as exc:
            db_error = str(exc)

    state = safe_json(STATE_PATH, {}) or {}
    geo = safe_json(GEO_FEED_PATH, {}) or {}
    config = {
        "trade_symbols": [x.strip() for x in str(os.getenv("TRADE_SYMBOLS") or "").split(",") if x.strip()],
        "alpaca_data_feed": os.getenv("ALPACA_DATA_FEED", "iex"),
        "check_interval_seconds": int(os.getenv("CHECK_INTERVAL_SECONDS", "60")),
        "max_trade_dollars": fnum(os.getenv("MAX_TRADE_DOLLARS", "0")),
        "max_total_exposure": fnum(os.getenv("MAX_TOTAL_EXPOSURE", "0")),
        "max_open_positions": int(os.getenv("MAX_OPEN_POSITIONS", "0")),
        "max_trades_per_day": int(os.getenv("MAX_TRADES_PER_DAY", "0")),
        "max_daily_realized_loss": fnum(os.getenv("MAX_DAILY_REALIZED_LOSS", "0")),
        "buy_score_threshold": fnum(os.getenv("BUY_SCORE_THRESHOLD", "0")),
        "sell_score_threshold": fnum(os.getenv("SELL_SCORE_THRESHOLD", "0")),
        "buy_confirmations": int(os.getenv("BUY_CONFIRMATIONS", "0")),
        "sell_confirmations": int(os.getenv("SELL_CONFIRMATIONS", "0")),
        "stop_loss_pct": fnum(os.getenv("STOP_LOSS_PCT", "0")),
        "take_profit_pct": fnum(os.getenv("TAKE_PROFIT_PCT", "0")),
        "trailing_stop_activation_pct": fnum(os.getenv("TRAILING_STOP_ACTIVATION_PCT", "0")),
        "trailing_stop_pct": fnum(os.getenv("TRAILING_STOP_PCT", "0")),
        "regime_shadow_enabled": str(os.getenv("REGIME_SHADOW_ENABLED", "1")).strip().lower() in {"1","true","yes","on"},
        "financial_leverage_shadow_enabled": str(os.getenv("FIN_LEVERAGE_SHADOW_ENABLED", "1")).strip().lower() in {"1","true","yes","on"},
        "financial_leverage_min_score": fnum(os.getenv("FIN_LEVERAGE_MIN_SCORE", "70")),
        "financial_leverage_outcome_horizons": os.getenv("FIN_LEVERAGE_OUTCOME_HORIZONS", "5,15,30,60"),
    }

    metrics = {
        "review_date": date_text,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paper_only": True,
        "coverage": {
            "db_path_exists": DB_PATH.exists(),
            "db_error": db_error,
            "daily_csv": summarize_daily_csv(date_text),
            "dashboard_state_exists": STATE_PATH.exists(),
            "geo_feed_exists": GEO_FEED_PATH.exists(),
        },
        "config": config,
        "decisions": summarize_decisions(decisions),
        "orders": summarize_orders(orders),
        "realized": summarize_realized(realized),
        "fills": {"rows": len(fills)},
        "decision_funnel_rows": len(funnel),
        "order_attempt_rows": len(order_attempts),
        "market_regime_shadow": summarize_market_regime(regime_rows),
        "regime_decision_shadow": summarize_regime_decisions(regime_decisions),
        "financial_leverage_shadow": summarize_financial_leverage(fin_rows, fin_signals, fin_outcomes),
        "decision_funnel": summarize_funnel(funnel),
        "order_attempts": summarize_order_attempts(order_attempts),
        "dashboard_snapshot": {
            "generated_at": state.get("generated_at"),
            "market_open": state.get("market_open"),
            "portfolio": state.get("portfolio") or {},
            "positions": state.get("positions") or [],
            "top_signals": sorted(state.get("signals") or [], key=lambda x: fnum(x.get("score")), reverse=True)[:9],
            "vix": state.get("vix") or {},
            "market_regime_shadow": state.get("market_regime_shadow") or {},
            "financial_leverage_shadow": state.get("financial_leverage_shadow") or {},
        },
        "geo": {
            "generated_at": geo.get("generated_at"),
            "status": geo.get("status"),
            "signal": geo.get("signal"),
            "score_adjustment": geo.get("score_adjustment"),
            "max_materiality": geo.get("max_materiality"),
            "active_event_count": geo.get("active_event_count"),
            "top_events": [
                {
                    "title": x.get("title"),
                    "source": x.get("source"),
                    "published_at": x.get("published_at"),
                    "analysis": x.get("analysis"),
                } for x in (geo.get("events") or [])[:6]
            ],
            "log_health": geo_log_health(),
        },
    }

    out_dir = DAILY_DIR / date_text
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "performance_input.json"
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics, path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(MARKET_TZ).date().isoformat())
    args = ap.parse_args()
    metrics, path = build(args.date)
    print(f"Built StockTracker review bundle: {path}")
    print(f"Decisions: {metrics['decisions']['rows']} | Orders: {metrics['orders']['rows']} | Realized: ${metrics['realized']['realized_pnl']:+.2f}")

if __name__ == "__main__":
    main()
