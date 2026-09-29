"""
ZPTA Specialist v0.1 — volatility-learning offshoot for StockTrader.

Shadow-only by design.  It studies ZPTA one-minute price/volume behavior,
records competing model forecasts, resolves their forward returns, and paper
trades an isolated virtual sleeve.  It never submits a broker order.

Data routing:
  1. Alpaca OTC feed when the account has the required OTC entitlement.
  2. Yahoo chart data as a delayed/research fallback.

This is experimental research software, not a validated profitable strategy.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import sqlite3
import statistics
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

SYMBOL = "ZPTA"
SHADOW_ONLY = True
BASE_DIR = Path(__file__).resolve().parent
MARKET_TZ = ZoneInfo("America/New_York")

# The module is imported before the parent trader loads configuration, so it
# must load the same split config/secret files itself.
load_dotenv(BASE_DIR / ".env.config")
load_dotenv(BASE_DIR / ".env", override=True)


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def project_path(name: str, default: str) -> Path:
    raw = os.getenv(name, "").strip()
    path = Path(raw).expanduser() if raw else BASE_DIR / default
    return path if path.is_absolute() else BASE_DIR / path


CHECK_SECONDS = int(os.getenv("ZPTA_CHECK_SECONDS", "60"))
ZPTA_SHADOW_ENABLED = env_bool("ZPTA_SHADOW_ENABLED", True)
DATA_PROVIDER = os.getenv("ZPTA_DATA_PROVIDER", "auto").strip().lower()
ALLOW_YAHOO_FALLBACK = env_bool("ZPTA_ALLOW_YAHOO_FALLBACK", True)
DB_PATH = project_path("ZPTA_DB_PATH", os.getenv("MULTI_DB_PATH", "momentum_trader.sqlite3"))
LOG_ROOT = project_path("ZPTA_LOG_ROOT", str(Path(os.getenv("MULTI_LOG_ROOT", "momentum_logs")) / "zpta"))
STATE_PATH = project_path("ZPTA_STATE_PATH", "zpta_state.json")

STARTING_CASH = float(os.getenv("ZPTA_SHADOW_STARTING_CASH", "1000"))
MAX_POSITION_DOLLARS = float(os.getenv("ZPTA_MAX_POSITION_DOLLARS", "150"))
MAX_POSITION_EQUITY_PCT = float(os.getenv("ZPTA_MAX_POSITION_EQUITY_PCT", "0.15"))
MAX_DAILY_LOSS_PCT = float(os.getenv("ZPTA_MAX_DAILY_LOSS_PCT", "0.03"))
MAX_TRADES_PER_DAY = int(os.getenv("ZPTA_MAX_TRADES_PER_DAY", "6"))
ENTRY_SCORE = float(os.getenv("ZPTA_ENTRY_SCORE", "68"))
EXIT_SCORE = float(os.getenv("ZPTA_EXIT_SCORE", "42"))
MIN_DOLLAR_VOLUME_5M = float(os.getenv("ZPTA_MIN_DOLLAR_VOLUME_5M", "25000"))
MAX_SPREAD_PROXY_PCT = float(os.getenv("ZPTA_MAX_SPREAD_PROXY_PCT", "0.08"))
MAX_ENTRY_SLIPPAGE_PCT = float(os.getenv("ZPTA_MAX_ENTRY_SLIPPAGE_PCT", "0.025"))
NO_NEW_ENTRIES_AFTER = os.getenv("ZPTA_NO_NEW_ENTRIES_AFTER", "15:30")
FLATTEN_AT = os.getenv("ZPTA_FLATTEN_AT", "15:45")

PUSHOVER_TOKEN = os.getenv("PUSHOVER_API_TOKEN") or os.getenv("PUSHOVER_APP_TOKEN")
PUSHOVER_USER = os.getenv("PUSHOVER_USER_KEY") or os.getenv("PUSHOVER_USER")
PUSHOVER_ENABLED = env_bool("ZPTA_PUSHOVER_ENABLED", True) and bool(PUSHOVER_TOKEN and PUSHOVER_USER)

ALPACA_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY", "").strip()
_PREFLIGHT_CACHE: dict[str, Any] = {"checked_at": 0.0, "result": None}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("zpta_specialist")


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    model: str
    score: float
    direction: str
    reason: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def market_now() -> datetime:
    return utc_now().astimezone(MARKET_TZ)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default


def pct(a: float, b: float) -> float:
    return safe_div(a, b, 1.0) - 1.0 if b else 0.0


def mean(values: Iterable[float], default: float = 0.0) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else default


def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    out = values[0]
    for value in values[1:]:
        out = alpha * value + (1.0 - alpha) * out
    return out


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return 50.0
    changes = [values[i] - values[i - 1] for i in range(len(values) - period, len(values))]
    gains = mean(max(v, 0.0) for v in changes)
    losses = mean(max(-v, 0.0) for v in changes)
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


def atr_pct(bars: list[Bar], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    sample = bars[-period:]
    trs = []
    previous = bars[-len(sample) - 1].close if len(bars) > len(sample) else sample[0].open
    for bar in sample:
        trs.append(max(bar.high - bar.low, abs(bar.high - previous), abs(bar.low - previous)))
        previous = bar.close
    return safe_div(mean(trs), sample[-1].close)


def vwap(bars: list[Bar]) -> float:
    dollars = sum(((b.high + b.low + b.close) / 3.0) * b.volume for b in bars)
    volume = sum(b.volume for b in bars)
    return safe_div(dollars, volume, bars[-1].close if bars else 0.0)


def session_bars(bars: list[Bar]) -> list[Bar]:
    if not bars:
        return []
    latest_day = bars[-1].ts.astimezone(MARKET_TZ).date()
    return [b for b in bars if b.ts.astimezone(MARKET_TZ).date() == latest_day]


def _request(url: str, *, params: dict[str, Any], headers: dict[str, str] | None = None) -> requests.Response:
    response = requests.get(url, params=params, headers=headers, timeout=20)
    response.raise_for_status()
    return response


def alpaca_asset_preflight() -> dict[str, Any]:
    if not (ALPACA_KEY and ALPACA_SECRET):
        return {"available": False, "reason": "Alpaca credentials not configured"}
    headers = {"APCA-API-KEY-ID": ALPACA_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET}
    try:
        response = _request(f"https://paper-api.alpaca.markets/v2/assets/{SYMBOL}", params={}, headers=headers)
        asset = response.json()
        return {
            "available": True,
            "symbol": asset.get("symbol"),
            "exchange": asset.get("exchange"),
            "status": asset.get("status"),
            "tradable": bool(asset.get("tradable")),
            "fractionable": bool(asset.get("fractionable")),
            "marginable": bool(asset.get("marginable")),
            "shortable": bool(asset.get("shortable")),
        }
    except Exception as exc:
        return {"available": False, "reason": f"asset preflight failed: {exc}"}


def cached_asset_preflight() -> dict[str, Any]:
    now = time.monotonic()
    if _PREFLIGHT_CACHE["result"] is None or now - float(_PREFLIGHT_CACHE["checked_at"]) >= 3600:
        _PREFLIGHT_CACHE["result"] = alpaca_asset_preflight()
        _PREFLIGHT_CACHE["checked_at"] = now
    return dict(_PREFLIGHT_CACHE["result"])


def fetch_alpaca_otc_bars() -> list[Bar]:
    if not (ALPACA_KEY and ALPACA_SECRET):
        raise RuntimeError("Alpaca credentials are not configured")
    headers = {"APCA-API-KEY-ID": ALPACA_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET}
    start = (utc_now() - timedelta(days=5)).isoformat().replace("+00:00", "Z")
    response = _request(
        f"https://data.alpaca.markets/v2/stocks/{SYMBOL}/bars",
        params={"timeframe": "1Min", "start": start, "limit": 10000, "feed": "otc", "adjustment": "all"},
        headers=headers,
    )
    payload = response.json()
    rows = payload.get("bars") or []
    if not rows:
        raise RuntimeError("Alpaca OTC returned no bars (OTC entitlement may be missing)")
    return [
        Bar(datetime.fromisoformat(row["t"].replace("Z", "+00:00")), float(row["o"]), float(row["h"]),
            float(row["l"]), float(row["c"]), float(row["v"]))
        for row in rows
    ]


def fetch_yahoo_bars() -> list[Bar]:
    response = _request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}",
        params={"interval": "1m", "range": "5d", "includePrePost": "false", "events": "div,splits"},
        headers={"User-Agent": "Mozilla/5.0 StockTrader research"},
    )
    result = response.json()["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    bars: list[Bar] = []
    for i, stamp in enumerate(timestamps):
        values = [quote.get(key, [None] * len(timestamps))[i] for key in ("open", "high", "low", "close", "volume")]
        if any(v is None for v in values):
            continue
        bars.append(Bar(datetime.fromtimestamp(stamp, timezone.utc), *(float(v) for v in values)))
    if not bars:
        raise RuntimeError("Yahoo fallback returned no one-minute bars")
    return bars


def fetch_bars() -> tuple[list[Bar], str]:
    errors = []
    if DATA_PROVIDER in {"auto", "alpaca_otc"}:
        try:
            return fetch_alpaca_otc_bars(), "alpaca_otc"
        except Exception as exc:
            errors.append(str(exc))
            if DATA_PROVIDER == "alpaca_otc" or not ALLOW_YAHOO_FALLBACK:
                raise
    if DATA_PROVIDER in {"auto", "yahoo"} or ALLOW_YAHOO_FALLBACK:
        try:
            return fetch_yahoo_bars(), "yahoo_delayed"
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors) or "No ZPTA data provider enabled")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS zpta_observations(
              ts TEXT PRIMARY KEY, provider TEXT, price REAL, volume REAL, features_json TEXT, regime TEXT);
            CREATE TABLE IF NOT EXISTS zpta_predictions(
              id TEXT PRIMARY KEY, created_ts TEXT, bar_ts TEXT, model TEXT, direction TEXT,
              score REAL, entry_price REAL, horizon_minutes INTEGER, due_ts TEXT,
              resolved_ts TEXT, exit_price REAL, forward_return REAL, correct INTEGER, reason TEXT);
            CREATE TABLE IF NOT EXISTS zpta_shadow_trades(
              id TEXT PRIMARY KEY, entry_ts TEXT, exit_ts TEXT, entry_price REAL, exit_price REAL,
              qty REAL, pnl REAL, pnl_pct REAL, entry_score REAL, exit_reason TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS zpta_daily_summaries(
              market_date TEXT PRIMARY KEY, created_ts TEXT, equity REAL, realized_pnl REAL,
              trades INTEGER, win_rate REAL, model_stats_json TEXT, provider TEXT);
            CREATE TABLE IF NOT EXISTS zpta_events(
              id TEXT PRIMARY KEY, ts TEXT, level TEXT, event TEXT, details_json TEXT);
            """
        )


def get_state() -> dict[str, Any]:
    default = {"cash": STARTING_CASH, "position": None, "equity_peak": STARTING_CASH, "last_bar_ts": None}
    if not STATE_PATH.exists():
        return default
    try:
        loaded = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return {**default, **loaded}
    except Exception:
        log.exception("State file unreadable; preserving it and starting safe flat state")
        return default


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(STATE_PATH)


def daily_paths() -> dict[str, Path]:
    folder = LOG_ROOT / market_now().date().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    return {"observations": folder / "observations.csv", "predictions": folder / "predictions.csv", "trades": folder / "trades.csv"}


def append_csv(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def add_event(level: str, event: str, details: dict[str, Any]) -> None:
    row = (str(uuid.uuid4()), utc_now().isoformat(), level, event, json.dumps(details, sort_keys=True))
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO zpta_events VALUES(?,?,?,?,?)", row)


def send_pushover(title: str, message: str) -> None:
    if not PUSHOVER_ENABLED:
        return
    try:
        requests.post("https://api.pushover.net/1/messages.json", data={
            "token": PUSHOVER_TOKEN, "user": PUSHOVER_USER, "title": title[:250], "message": message[:1024]
        }, timeout=10).raise_for_status()
    except Exception:
        log.exception("ZPTA Pushover alert failed")


def build_features(bars: list[Bar]) -> dict[str, float]:
    current = session_bars(bars)
    if len(current) < 10:
        raise RuntimeError(f"Need at least 10 current-session trade bars; received {len(current)}")
    closes = [b.close for b in current]
    vols = [b.volume for b in current]
    latest = current[-1]

    # OTC trade bars can be sparse.  Lookbacks are measured in clock minutes,
    # not "N observed bars", so five prints spread across an hour are never
    # mistaken for five-minute momentum.
    def bars_since(minutes: int) -> list[Bar]:
        cutoff = latest.ts - timedelta(minutes=minutes)
        return [b for b in current if b.ts >= cutoff]

    def close_minutes_ago(minutes: int) -> float:
        cutoff = latest.ts - timedelta(minutes=minutes)
        candidates = [b.close for b in current if b.ts <= cutoff]
        return candidates[-1] if candidates else current[0].close

    first_stamp = current[0].ts.astimezone(MARKET_TZ).replace(hour=9, minute=30, second=0, microsecond=0)
    first_30 = [b for b in current if b.ts.astimezone(MARKET_TZ) <= first_stamp + timedelta(minutes=30)] or current[:1]
    rolling_20m = bars_since(20)
    rolling_high = max(b.high for b in rolling_20m)
    rolling_low = min(b.low for b in rolling_20m)
    bar_range = max(latest.high - latest.low, latest.close * 0.001)
    median_volume = statistics.median(vols[-21:-1]) if len(vols) > 21 else statistics.median(vols[:-1])
    dollar_volume_5m = sum(b.close * b.volume for b in bars_since(5))
    session_vwap = vwap(current)
    atr = atr_pct(current)
    spread_proxy = clamp(mean((b.high - b.low) / b.close for b in current[-5:] if b.close), 0.002, 0.25)
    return {
        "price": latest.close,
        "ret_1m": pct(closes[-1], close_minutes_ago(1)),
        "ret_3m": pct(closes[-1], close_minutes_ago(3)),
        "ret_5m": pct(closes[-1], close_minutes_ago(5)),
        "ret_15m": pct(closes[-1], close_minutes_ago(15)),
        "ema9_gap": pct(latest.close, ema(closes[-40:], 9)),
        "ema20_gap": pct(latest.close, ema(closes[-60:], 20)),
        "vwap_gap": pct(latest.close, session_vwap),
        "rsi14": rsi(closes),
        "atr_pct": atr,
        "rel_volume": safe_div(latest.volume, median_volume, 1.0),
        "dollar_volume_5m": dollar_volume_5m,
        "range_position_20": safe_div(latest.close - rolling_low, rolling_high - rolling_low, 0.5),
        "opening_range_position": safe_div(latest.close - min(b.low for b in first_30), max(b.high for b in first_30) - min(b.low for b in first_30), 0.5),
        "upper_wick": safe_div(latest.high - max(latest.open, latest.close), bar_range),
        "lower_wick": safe_div(min(latest.open, latest.close) - latest.low, bar_range),
        "spread_proxy_pct": spread_proxy,
        "session_return": pct(latest.close, current[0].open),
        "trade_bars_5m": float(len(bars_since(5))),
        "history_coverage_minutes": (latest.ts - current[0].ts).total_seconds() / 60.0,
    }


def classify_regime(features: dict[str, float]) -> str:
    if (features["dollar_volume_5m"] < MIN_DOLLAR_VOLUME_5M
            or features["spread_proxy_pct"] > MAX_SPREAD_PROXY_PCT
            or features["trade_bars_5m"] < 2):
        return "LIQUIDITY_DANGER"
    aligned = features["ema9_gap"] > 0 and features["ema20_gap"] > 0 and features["vwap_gap"] > 0
    if aligned and features["rel_volume"] >= 1.25:
        return "MOMENTUM_UP"
    if features["atr_pct"] >= 0.04 and abs(features["ret_5m"]) < features["atr_pct"] * 0.35:
        return "VOLATILE_CHOP"
    return "NEUTRAL"


def score_models(features: dict[str, float], regime: str) -> list[Signal]:
    f = features
    signals: list[Signal] = []

    breakout = 35 + 18 * clamp(f["range_position_20"], 0, 1) + 10 * clamp(f["opening_range_position"], 0, 1)
    breakout += 12 * clamp((f["rel_volume"] - 1) / 2, 0, 1) + 10 * clamp(f["ret_5m"] / 0.05, -1, 1)
    breakout -= 12 * clamp(f["upper_wick"], 0, 1)
    signals.append(Signal("breakout_continuation", clamp(breakout, 0, 100), "UP", "20m/opening-range breakout with volume"))

    pullback = 45 + 18 * clamp(f["ret_15m"] / 0.08, -1, 1) - 14 * clamp(f["ret_3m"] / 0.04, -1, 1)
    pullback += 12 * clamp(f["lower_wick"], 0, 1) + 8 * clamp((f["rel_volume"] - 0.8) / 2, 0, 1)
    if f["vwap_gap"] < -0.04:
        pullback -= 14
    signals.append(Signal("momentum_pullback", clamp(pullback, 0, 100), "UP", "intraday uptrend pullback and lower-wick recovery"))

    reclaim = 48 + 24 * clamp(f["vwap_gap"] / 0.035, -1, 1) + 12 * clamp(f["ret_3m"] / 0.03, -1, 1)
    reclaim += 8 * clamp((f["rel_volume"] - 1) / 2, 0, 1)
    signals.append(Signal("vwap_reclaim", clamp(reclaim, 0, 100), "UP", "VWAP reclaim with short-term acceleration"))

    exhaustion = 35 + 20 * clamp((f["rsi14"] - 55) / 35, -1, 1) + 20 * clamp(f["upper_wick"], 0, 1)
    exhaustion += 12 * clamp(f["ret_15m"] / 0.12, -1, 1) - 12 * clamp(f["ret_1m"] / 0.025, -1, 1)
    signals.append(Signal("exhaustion_exit", clamp(exhaustion, 0, 100), "DOWN", "overextension and upper-wick reversal risk"))

    if regime == "LIQUIDITY_DANGER":
        signals = [Signal(s.model, min(s.score, 45) if s.direction == "UP" else s.score, s.direction, s.reason) for s in signals]
    elif regime == "MOMENTUM_UP":
        signals = [Signal(s.model, clamp(s.score + (6 if s.direction == "UP" else -3), 0, 100), s.direction, s.reason) for s in signals]
    return signals


def ensemble_score(signals: list[Signal]) -> float:
    up = [s.score for s in signals if s.direction == "UP"]
    down = [s.score for s in signals if s.direction == "DOWN"]
    return clamp(0.72 * mean(up, 50) + 0.28 * (100 - mean(down, 50)), 0, 100)


def record_observation(bar: Bar, provider: str, features: dict[str, float], regime: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO zpta_observations VALUES(?,?,?,?,?,?)",
            (bar.ts.isoformat(), provider, bar.close, bar.volume, json.dumps(features, sort_keys=True), regime),
        )
    append_csv(daily_paths()["observations"], {
        "ts": bar.ts.isoformat(), "provider": provider, "price": bar.close, "regime": regime, **features
    })


def record_predictions(bar: Bar, signals: list[Signal]) -> None:
    rows = []
    for signal in signals:
        for horizon in (5, 15, 60):
            row = {
                "id": str(uuid.uuid4()), "created_ts": utc_now().isoformat(), "bar_ts": bar.ts.isoformat(),
                "model": signal.model, "direction": signal.direction, "score": round(signal.score, 4),
                "entry_price": bar.close, "horizon_minutes": horizon,
                "due_ts": (bar.ts + timedelta(minutes=horizon)).isoformat(), "resolved_ts": None,
                "exit_price": None, "forward_return": None, "correct": None, "reason": signal.reason,
            }
            rows.append(row)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            "INSERT INTO zpta_predictions VALUES(:id,:created_ts,:bar_ts,:model,:direction,:score,:entry_price,:horizon_minutes,:due_ts,:resolved_ts,:exit_price,:forward_return,:correct,:reason)",
            rows,
        )
    for row in rows:
        append_csv(daily_paths()["predictions"], row)


def resolve_predictions(bars: list[Bar]) -> int:
    if not bars:
        return 0
    resolved = 0
    latest_ts = bars[-1].ts
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        pending = conn.execute(
            "SELECT * FROM zpta_predictions WHERE resolved_ts IS NULL AND due_ts <= ? ORDER BY due_ts LIMIT 500",
            (latest_ts.isoformat(),),
        ).fetchall()
        for row in pending:
            due = datetime.fromisoformat(row["due_ts"])
            candidates = [b for b in bars if b.ts >= due]
            if not candidates:
                continue
            exit_bar = candidates[0]
            forward = pct(exit_bar.close, float(row["entry_price"]))
            correct = int(forward > 0) if row["direction"] == "UP" else int(forward < 0)
            conn.execute(
                "UPDATE zpta_predictions SET resolved_ts=?, exit_price=?, forward_return=?, correct=? WHERE id=?",
                (utc_now().isoformat(), exit_bar.close, forward, correct, row["id"]),
            )
            resolved += 1
    return resolved


def trades_today() -> int:
    day = market_now().date().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM zpta_shadow_trades WHERE substr(entry_ts,1,10)=?", (day,)).fetchone()[0])


def realized_today() -> float:
    day = market_now().date().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        value = conn.execute("SELECT COALESCE(SUM(pnl),0) FROM zpta_shadow_trades WHERE substr(exit_ts,1,10)=?", (day,)).fetchone()[0]
    return float(value or 0.0)


def time_at_or_after(hhmm: str, now: datetime | None = None) -> bool:
    now = now or market_now()
    hour, minute = (int(v) for v in hhmm.split(":"))
    return (now.hour, now.minute) >= (hour, minute)


def paper_fill(price: float, spread_proxy: float, side: str) -> float:
    half_spread = min(spread_proxy / 2.0, MAX_ENTRY_SLIPPAGE_PCT)
    return price * (1.0 + half_spread if side == "buy" else 1.0 - half_spread)


def maybe_trade(bar: Bar, features: dict[str, float], regime: str, score: float, state: dict[str, Any]) -> str:
    position = state.get("position")
    price = bar.close
    spread = features["spread_proxy_pct"]
    if position:
        entry = float(position["entry_price"])
        high_water = max(float(position.get("high_water", entry)), price)
        position["high_water"] = high_water
        gain = pct(price, entry)
        atr_stop = clamp(features["atr_pct"] * 1.6, 0.04, 0.10)
        trailing = price <= high_water * (1.0 - clamp(features["atr_pct"] * 1.25, 0.035, 0.08)) and gain > 0.04
        exit_reason = None
        if gain <= -atr_stop:
            exit_reason = "ATR_STOP"
        elif trailing:
            exit_reason = "VOLATILITY_TRAIL"
        elif score <= EXIT_SCORE:
            exit_reason = "ENSEMBLE_REVERSAL"
        elif time_at_or_after(FLATTEN_AT):
            exit_reason = "NO_OVERNIGHT"
        if exit_reason:
            fill = paper_fill(price, spread, "sell")
            qty = float(position["qty"])
            proceeds = fill * qty
            pnl = proceeds - entry * qty
            state["cash"] = float(state["cash"]) + proceeds
            row = {
                "id": position["id"], "entry_ts": position["entry_ts"], "exit_ts": market_now().isoformat(),
                "entry_price": entry, "exit_price": fill, "qty": qty, "pnl": pnl,
                "pnl_pct": pct(fill, entry), "entry_score": position["entry_score"],
                "exit_reason": exit_reason, "status": "CLOSED",
            }
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("UPDATE zpta_shadow_trades SET exit_ts=?,exit_price=?,pnl=?,pnl_pct=?,exit_reason=?,status='CLOSED' WHERE id=?",
                             (row["exit_ts"], fill, pnl, row["pnl_pct"], exit_reason, position["id"]))
            append_csv(daily_paths()["trades"], row)
            state["position"] = None
            send_pushover("ZPTA shadow SELL", f"{qty:.2f} shares @ ${fill:.4f}\nP/L ${pnl:+.2f} ({row['pnl_pct']:+.1%})\n{exit_reason}")
            return exit_reason
        return "HOLD"

    equity = float(state["cash"])
    loss_limit = -STARTING_CASH * MAX_DAILY_LOSS_PCT
    blocked = (
        regime == "LIQUIDITY_DANGER" or score < ENTRY_SCORE or time_at_or_after(NO_NEW_ENTRIES_AFTER)
        or trades_today() >= MAX_TRADES_PER_DAY or realized_today() <= loss_limit
        or spread > MAX_SPREAD_PROXY_PCT
    )
    if blocked:
        return "FLAT"
    allocation = min(MAX_POSITION_DOLLARS, equity * MAX_POSITION_EQUITY_PCT, float(state["cash"]))
    fill = paper_fill(price, spread, "buy")
    qty = math.floor(allocation / fill)
    if qty < 1:
        return "FLAT_INSUFFICIENT_CASH"
    cost = qty * fill
    trade_id = str(uuid.uuid4())
    entry_ts = market_now().isoformat()
    state["cash"] = float(state["cash"]) - cost
    state["position"] = {"id": trade_id, "entry_ts": entry_ts, "entry_price": fill, "qty": qty, "high_water": fill, "entry_score": score}
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO zpta_shadow_trades VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (trade_id, entry_ts, None, fill, None, qty, None, None, score, None, "OPEN"))
    append_csv(daily_paths()["trades"], {
        "id": trade_id, "entry_ts": entry_ts, "exit_ts": "", "entry_price": fill, "exit_price": "",
        "qty": qty, "pnl": "", "pnl_pct": "", "entry_score": score, "exit_reason": "", "status": "OPEN"
    })
    send_pushover("ZPTA shadow BUY", f"{qty} shares @ ${fill:.4f}\nScore {score:.1f} | {regime}\nShadow only—no broker order")
    return "SHADOW_BUY"


def write_daily_summary(provider: str, state: dict[str, Any], mark: float) -> None:
    market_date = market_now().date().isoformat()
    position = state.get("position")
    equity = float(state["cash"]) + (float(position["qty"]) * mark if position else 0.0)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        model_rows = conn.execute(
            "SELECT model,horizon_minutes,COUNT(*) n,AVG(correct) accuracy,AVG(forward_return) avg_return "
            "FROM zpta_predictions WHERE resolved_ts IS NOT NULL GROUP BY model,horizon_minutes"
        ).fetchall()
        closed = conn.execute("SELECT pnl FROM zpta_shadow_trades WHERE status='CLOSED'").fetchall()
        stats = [dict(row) for row in model_rows]
        wins = sum(1 for row in closed if float(row[0]) > 0)
        win_rate = safe_div(wins, len(closed))
        conn.execute(
            "INSERT OR REPLACE INTO zpta_daily_summaries VALUES(?,?,?,?,?,?,?,?)",
            (market_date, utc_now().isoformat(), equity, realized_today(), trades_today(), win_rate, json.dumps(stats), provider),
        )


def run_once() -> dict[str, Any]:
    if not ZPTA_SHADOW_ENABLED:
        return {"status": "DISABLED", "shadow_only": True}
    init_db()
    bars, provider = fetch_bars()
    current = session_bars(bars)
    latest = current[-1]
    state = get_state()
    if state.get("last_bar_ts") == latest.ts.isoformat():
        resolve_predictions(bars)
        return {"status": "NO_NEW_BAR", "provider": provider, "bar_ts": latest.ts.isoformat()}
    features = build_features(bars)
    regime = classify_regime(features)
    signals = score_models(features, regime)
    score = ensemble_score(signals)
    record_observation(latest, provider, features, regime)
    record_predictions(latest, signals)
    resolved = resolve_predictions(bars)
    action = maybe_trade(latest, features, regime, score, state)
    state["last_bar_ts"] = latest.ts.isoformat()
    position = state.get("position")
    equity = float(state["cash"]) + (float(position["qty"]) * latest.close if position else 0.0)
    state["equity_peak"] = max(float(state.get("equity_peak", equity)), equity)
    save_state(state)
    write_daily_summary(provider, state, latest.close)
    output = {
        "status": "OK", "shadow_only": SHADOW_ONLY, "provider": provider, "bar_ts": latest.ts.isoformat(),
        "price": latest.close, "regime": regime, "ensemble_score": round(score, 2), "action": action,
        "resolved_predictions": resolved, "equity": round(equity, 2),
        "signals": [asdict(s) for s in signals], "asset_preflight": cached_asset_preflight(),
    }
    log.info(json.dumps(output, sort_keys=True))
    return output


def self_test() -> None:
    start = utc_now().replace(hour=14, minute=30, second=0, microsecond=0)
    bars = []
    price = 0.70
    for i in range(90):
        drift = 0.0015 if i < 55 else (-0.0005 if i < 70 else 0.0025)
        wave = math.sin(i / 4.0) * 0.003
        open_price = price
        price = max(0.05, price * (1 + drift + wave))
        bars.append(Bar(start + timedelta(minutes=i), open_price, max(open_price, price) * 1.006,
                        min(open_price, price) * 0.994, price, 5000 + i * 120))
    features = build_features(bars)
    regime = classify_regime(features)
    signals = score_models(features, regime)
    assert 0 <= ensemble_score(signals) <= 100
    assert len(signals) == 4
    assert features["price"] > 0
    print(json.dumps({"self_test": "PASS", "regime": regime, "score": ensemble_score(signals)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="ZPTA shadow specialist for StockTrader")
    parser.add_argument("--once", action="store_true", help="Process one cycle and exit")
    parser.add_argument("--self-test", action="store_true", help="Run deterministic tests without network or credentials")
    parser.add_argument("--preflight", action="store_true", help="Show Alpaca ZPTA asset eligibility and exit")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    init_db()
    if args.preflight:
        print(json.dumps(alpaca_asset_preflight(), indent=2))
        return
    while True:
        try:
            result = run_once()
            if args.once:
                print(json.dumps(result, indent=2))
                return
        except KeyboardInterrupt:
            return
        except Exception as exc:
            log.exception("ZPTA specialist cycle failed")
            add_event("ERROR", "cycle_failed", {"error": str(exc)})
            if args.once:
                raise
        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()
