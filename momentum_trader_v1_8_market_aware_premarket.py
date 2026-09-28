"""
Momentum Trader v1.8 — PAPER-ONLY market-aware trader with premarket intelligence, decision funnel, SHADOW regime, and leveraged-financial research.

Tradable: XOM, WMT, AMZN, AAPL, NVDA, TSLA, SPY, QQQ, GLD
Context: SPY, QQQ, GLD, USO, VIX (^VIX via Yahoo chart endpoint; VIXY fallback)

Design:
- Per-symbol technical score: SMA20 distance, 5m/15m momentum, RSI14, relative volume.
- Cross-market context: SPY/QQQ/GLD/USO plus VIX level/change.
- XOM also consumes geo_feed.json from xom_geo_feed.py.
- Per-symbol confirmation counters, stops, take profit, trailing stop.
- Portfolio limits across all positions.
- SQLite audit trail + dashboard_state.json + daily CSV logs.
- PAPER ONLY. Refuses live trading.

This is experimental software, not a validated profitable strategy.
"""
from __future__ import annotations

import csv, json, logging, math, os, sqlite3, time, uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from alpaca.common.exceptions import APIError
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / ".env.config"
SECRETS_FILE = BASE_DIR / ".env"

# Split configuration: committed non-secret settings first, local secrets override.
load_dotenv(CONFIG_FILE)
load_dotenv(SECRETS_FILE, override=True)

# ---------------- Configuration ----------------
PAPER_ONLY = True
TRADE_SYMBOLS = [s.strip().upper() for s in os.getenv(
    "TRADE_SYMBOLS", "XOM,WMT,AMZN,AAPL,NVDA,TSLA,SPY,QQQ,GLD"
).split(",") if s.strip()]
CONTEXT_SYMBOLS = ["SPY", "QQQ", "GLD", "USO"]
SHADOW_FINANCIAL_SYMBOLS = ["XLF", "FAS", "FAZ"]
VIX_FALLBACK_SYMBOL = os.getenv("VIX_FALLBACK_SYMBOL", "VIXY")

ALPACA_API_KEY = os.environ["ALPACA_API_KEY"]
ALPACA_SECRET_KEY = os.environ["ALPACA_SECRET_KEY"]
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
PREMARKET_ENABLED = str(os.getenv("PREMARKET_ENABLED", "1")).strip().lower() in {"1","true","yes","y","on"}
PREMARKET_START_MINUTES = int(os.getenv("PREMARKET_START_MINUTES", "30"))
PREMARKET_REFRESH_OFFSETS = tuple(sorted({int(x) for x in os.getenv("PREMARKET_REFRESH_OFFSETS", "30,20,10,5,1").split(",") if x.strip()}, reverse=True))
PREMARKET_CONTEXT_MAX_ADJ = float(os.getenv("PREMARKET_CONTEXT_MAX_ADJ", "5"))
PREMARKET_CONTEXT_ACTIVE_MINUTES = int(os.getenv("PREMARKET_CONTEXT_ACTIVE_MINUTES", "60"))
PREMARKET_SOCIAL_SOURCE = os.getenv("PREMARKET_SOCIAL_SOURCE", "UNAVAILABLE").strip() or "UNAVAILABLE"
MARKET_OPEN_WARMUP_MINUTES = int(os.getenv("MARKET_OPEN_WARMUP_MINUTES", "20"))
CLOSED_IDLE_MAX_SLEEP_SECONDS = int(os.getenv("CLOSED_IDLE_MAX_SLEEP_SECONDS", "21600"))

# Alpaca equities market-data feed. Set ALPACA_DATA_FEED=iex for Basic/free
# accounts or ALPACA_DATA_FEED=sip for accounts entitled to real-time SIP.
ALPACA_DATA_FEED_NAME = os.getenv("ALPACA_DATA_FEED", "iex").strip().lower()
_DATA_FEEDS = {"iex": DataFeed.IEX, "sip": DataFeed.SIP}
if ALPACA_DATA_FEED_NAME not in _DATA_FEEDS:
    raise ValueError("ALPACA_DATA_FEED must be either 'iex' or 'sip'")
ALPACA_DATA_FEED = _DATA_FEEDS[ALPACA_DATA_FEED_NAME]

MAX_TRADE_DOLLARS = float(os.getenv("MAX_TRADE_DOLLARS", "2500"))
MAX_TOTAL_EXPOSURE = float(os.getenv("MAX_TOTAL_EXPOSURE", "10000"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "4"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "12"))
MAX_DAILY_REALIZED_LOSS = float(os.getenv("MAX_DAILY_REALIZED_LOSS", "300"))

BUY_SCORE_THRESHOLD = float(os.getenv("BUY_SCORE_THRESHOLD", "70"))
SELL_SCORE_THRESHOLD = float(os.getenv("SELL_SCORE_THRESHOLD", "30"))
BUY_CONFIRMATIONS = int(os.getenv("BUY_CONFIRMATIONS", "2"))
SELL_CONFIRMATIONS = int(os.getenv("SELL_CONFIRMATIONS", "2"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.02"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.03"))
TRAILING_STOP_ACTIVATION_PCT = float(os.getenv("TRAILING_STOP_ACTIVATION_PCT", "0.01"))
TRAILING_STOP_PCT = float(os.getenv("TRAILING_STOP_PCT", "0.0125"))

# SHADOW market-regime research. These settings NEVER alter order execution.
REGIME_SHADOW_ENABLED = str(os.getenv("REGIME_SHADOW_ENABLED", "1")).strip().lower() in {"1","true","yes","y","on"}
REGIME_RISK_ON_MIN = float(os.getenv("REGIME_RISK_ON_MIN", "70"))
REGIME_NEUTRAL_MIN = float(os.getenv("REGIME_NEUTRAL_MIN", "40"))
REGIME_SPY_200_BUFFER_PCT = float(os.getenv("REGIME_SPY_200_BUFFER_PCT", "0.01"))
REGIME_QQQ_200_BUFFER_PCT = float(os.getenv("REGIME_QQQ_200_BUFFER_PCT", "0.01"))
REGIME_VIX_MAX_RISK_ON = float(os.getenv("REGIME_VIX_MAX_RISK_ON", "25"))
REGIME_TREND_CACHE_SECONDS = int(os.getenv("REGIME_TREND_CACHE_SECONDS", "900"))
REGIME_SHADOW_LOG_INTERVAL_SECONDS = int(os.getenv("REGIME_SHADOW_LOG_INTERVAL_SECONDS", "300"))
REGIME_SHADOW_DEFENSIVE_ASSET = os.getenv("REGIME_SHADOW_DEFENSIVE_ASSET", "SGOV").strip().upper() or "SGOV"

# SHADOW-only FAS/FAZ research. These symbols are NOT added to TRADE_SYMBOLS.
FIN_LEVERAGE_SHADOW_ENABLED = str(os.getenv("FIN_LEVERAGE_SHADOW_ENABLED", "1")).strip().lower() in {"1","true","yes","y","on"}
FIN_LEVERAGE_SNAPSHOT_SECONDS = int(os.getenv("FIN_LEVERAGE_SNAPSHOT_SECONDS", "300"))
FIN_LEVERAGE_SIGNAL_COOLDOWN_SECONDS = int(os.getenv("FIN_LEVERAGE_SIGNAL_COOLDOWN_SECONDS", "900"))
FIN_LEVERAGE_MIN_SCORE = float(os.getenv("FIN_LEVERAGE_MIN_SCORE", "70"))
FIN_LEVERAGE_OUTCOME_HORIZONS = tuple(int(x) for x in os.getenv("FIN_LEVERAGE_OUTCOME_HORIZONS", "5,15,30,60").split(",") if x.strip())


def project_path(env_name, default_name):
    raw = os.getenv(env_name, "").strip()
    p = Path(raw).expanduser() if raw else (BASE_DIR / default_name)
    return p if p.is_absolute() else (BASE_DIR / p)

DB_PATH = project_path("MULTI_DB_PATH", "momentum_trader.sqlite3")
LOG_ROOT = project_path("MULTI_LOG_ROOT", "momentum_logs")
STATE_PATH = project_path("DASHBOARD_STATE_PATH", "dashboard_state.json")
GEO_FEED_PATH = project_path("GEO_FEED_PATH", "geo_feed.json")
GEO_FEED_MAX_AGE_MINUTES = int(os.getenv("GEO_FEED_MAX_AGE_MINUTES", "15"))
GEO_MAX_SCORE_ADJUSTMENT = float(os.getenv("GEO_MAX_SCORE_ADJUSTMENT", "10"))
MARKET_TZ = ZoneInfo("America/New_York")

PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN") or os.getenv("PUSHOVER_APP_TOKEN") or os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY") or os.getenv("PUSHOVER_USER")
PUSHOVER_ENABLED = bool(PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY)

# Dedicated Stock EOD Pushover application. Existing trade/movement alerts above
# are intentionally unchanged and continue to use PUSHOVER_API_TOKEN.
PUSHOVER_STOCK_EOD_ENABLED = str(os.getenv("PUSHOVER_STOCK_EOD_ENABLED", "1")).strip().lower() in {"1","true","yes","y","on"}
PUSHOVER_STOCK_EOD_TOKEN = os.getenv("PUSHOVER_STOCK_EOD_TOKEN")
PUSHOVER_STOCK_EOD_USER_KEY = os.getenv("PUSHOVER_STOCK_EOD_USER_KEY") or PUSHOVER_USER_KEY
PUSHOVER_STOCK_EOD_HOUR = int(os.getenv("PUSHOVER_STOCK_EOD_HOUR", "16"))
PUSHOVER_STOCK_EOD_MINUTE = int(os.getenv("PUSHOVER_STOCK_EOD_MINUTE", "10"))
STOCK_EOD_STATE_PATH = project_path("STOCK_EOD_STATE_PATH", "stock_eod_report_state.json")
PREMARKET_STATE_PATH = project_path("PREMARKET_STATE_PATH", "premarket_state.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("momentum_trader")

if not PAPER_ONLY:
    raise RuntimeError("This program is intentionally PAPER ONLY.")

trading = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

_REGIME_TREND_CACHE = {"fetched_at": 0.0, "value": None}
_LAST_REGIME_LOG = {"ts": 0.0, "state": None}
_LAST_FIN_LEVERAGE_LOG = {"ts": 0.0}
_LAST_FIN_LEVERAGE_SIGNAL = {"ts": 0.0, "candidate": None}
_PREMARKET_CONTEXT = {"session_date": None, "bias": "UNAVAILABLE", "bias_score": 50.0, "generated_at": None, "status": "UNAVAILABLE"}
_LAST_IDLE_TARGET = None

# ---------------- Helpers ----------------
def utc_now(): return datetime.now(timezone.utc)
def market_now(): return datetime.now(MARKET_TZ)
def clamp(v, lo, hi): return max(lo, min(hi, v))
def pct_change(a, b): return (a / b - 1.0) if b else 0.0

def sma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None

def rsi(vals, n=14):
    if len(vals) < n + 1: return 50.0
    ds = [vals[i] - vals[i-1] for i in range(len(vals)-n, len(vals))]
    gains = sum(max(x,0) for x in ds) / n
    losses = sum(max(-x,0) for x in ds) / n
    if losses == 0: return 100.0
    rs = gains / losses
    return 100 - 100/(1+rs)

def send_pushover(title, message):
    if not PUSHOVER_ENABLED: return
    try:
        requests.post("https://api.pushover.net/1/messages.json", data={
            "token": PUSHOVER_API_TOKEN, "user": PUSHOVER_USER_KEY,
            "title": title, "message": message[:1024]
        }, timeout=10).raise_for_status()
    except Exception:
        log.exception("Pushover failed")

def send_stock_eod_pushover(title, message):
    """Use the dedicated Stock EOD Pushover app/token only."""
    if not PUSHOVER_STOCK_EOD_ENABLED:
        return False
    if not PUSHOVER_STOCK_EOD_TOKEN or not PUSHOVER_STOCK_EOD_USER_KEY:
        return False
    try:
        requests.post("https://api.pushover.net/1/messages.json", data={
            "token": PUSHOVER_STOCK_EOD_TOKEN,
            "user": PUSHOVER_STOCK_EOD_USER_KEY,
            "title": str(title)[:250],
            "message": str(message)[:1024],
        }, timeout=10).raise_for_status()
        return True
    except Exception:
        log.exception("Stock EOD Pushover failed")
        return False


def load_stock_eod_state():
    if not STOCK_EOD_STATE_PATH.exists():
        return {}
    try:
        return json.loads(STOCK_EOD_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_stock_eod_state(state):
    tmp = STOCK_EOD_STATE_PATH.with_suffix(STOCK_EOD_STATE_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STOCK_EOD_STATE_PATH)


def daily_paths():
    d = LOG_ROOT / market_now().date().isoformat(); d.mkdir(parents=True, exist_ok=True)
    return {
        "folder": d,
        "decisions": d/"decisions.csv",
        "trades": d/"trades.csv",
        "decision_funnel": d/"decision_funnel.csv",
        "order_attempts": d/"order_attempts.csv",
        "market_regime_shadow": d/"market_regime_shadow.csv",
        "regime_decision_shadow": d/"regime_decision_shadow.csv",
        "financial_leverage_shadow": d/"financial_leverage_shadow.csv",
        "financial_leverage_signals": d/"financial_leverage_signals.csv",
        "financial_leverage_outcomes": d/"financial_leverage_outcomes.csv",
        "premarket_intelligence": d/"premarket_intelligence.csv",
        "premarket_symbols": d/"premarket_symbols.csv",
    }

def append_csv(path, row):
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists: w.writeheader()
        w.writerow(row)

# ---------------- DB ----------------
def db_connect():
    c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row; return c

def init_db():
    with db_connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS decisions(
          id TEXT PRIMARY KEY, ts TEXT, symbol TEXT, price REAL, score REAL, decision TEXT,
          technical REAL, context REAL, vix_adjustment REAL, geo_adjustment REAL,
          momentum_5m REAL, momentum_15m REAL, rsi14 REAL, volume_ratio REAL,
          vix_level REAL, vix_5m REAL, vix_15m REAL, reason TEXT);
        CREATE TABLE IF NOT EXISTS orders(
          id TEXT PRIMARY KEY, ts TEXT, symbol TEXT, side TEXT, qty REAL, price REAL,
          notional REAL, reason TEXT, alpaca_order_id TEXT);
        CREATE TABLE IF NOT EXISTS fills(
          alpaca_order_id TEXT PRIMARY KEY, ts TEXT, symbol TEXT, side TEXT, qty REAL, price REAL);
        CREATE TABLE IF NOT EXISTS realized(
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, symbol TEXT, pnl REAL);
        CREATE TABLE IF NOT EXISTS decision_funnel(
          event_id TEXT PRIMARY KEY, ts TEXT, symbol TEXT, side TEXT,
          score REAL, threshold REAL, raw_threshold_cross INTEGER,
          confirmation_count INTEGER, confirmation_required INTEGER,
          position_state TEXT, projected_exposure REAL, open_position_count INTEGER,
          market_open INTEGER, model_decision TEXT, final_disposition TEXT,
          gate_reason TEXT, decision_reason TEXT);
        CREATE TABLE IF NOT EXISTS order_attempts(
          attempt_id TEXT PRIMARY KEY, ts TEXT, decision_event_id TEXT,
          symbol TEXT, side TEXT, attempted INTEGER, accepted INTEGER,
          gate_reason TEXT, alpaca_order_id TEXT);
        CREATE TABLE IF NOT EXISTS market_regime_shadow(
          id TEXT PRIMARY KEY, ts TEXT, regime_state TEXT, regime_score REAL,
          spy_close REAL, spy_sma50 REAL, spy_sma200 REAL, spy_mom20 REAL,
          qqq_close REAL, qqq_sma200 REAL, vix_level REAL,
          defensive_asset TEXT, reasons_json TEXT);
        CREATE TABLE IF NOT EXISTS regime_decision_shadow(
          id TEXT PRIMARY KEY, ts TEXT, decision_event_id TEXT, symbol TEXT,
          model_decision TEXT, score REAL, regime_state TEXT, regime_score REAL,
          shadow_action TEXT, defensive_asset TEXT);
        CREATE TABLE IF NOT EXISTS financial_leverage_shadow(
          id TEXT PRIMARY KEY, ts TEXT, regime_state TEXT, regime_score REAL,
          candidate TEXT, candidate_score REAL, xlf_price REAL, xlf_mom5 REAL, xlf_mom15 REAL,
          fas_price REAL, fas_mom5 REAL, fas_mom15 REAL,
          faz_price REAL, faz_mom5 REAL, faz_mom15 REAL,
          vix_level REAL, vix_15m REAL, reasons_json TEXT);
        CREATE TABLE IF NOT EXISTS financial_leverage_signals(
          signal_id TEXT PRIMARY KEY, ts TEXT, candidate TEXT, candidate_score REAL,
          regime_state TEXT, regime_score REAL, xlf_price REAL, fas_price REAL, faz_price REAL,
          vix_level REAL, reasons_json TEXT);
        CREATE TABLE IF NOT EXISTS financial_leverage_outcomes(
          id TEXT PRIMARY KEY, signal_id TEXT, observed_at TEXT, horizon_minutes INTEGER,
          candidate TEXT, candidate_return REAL, xlf_return REAL, fas_return REAL, faz_return REAL);
        CREATE TABLE IF NOT EXISTS premarket_intelligence(
          id TEXT PRIMARY KEY, session_date TEXT, scheduled_offset_minutes INTEGER,
          ts TEXT, bias TEXT, bias_score REAL, regime_state TEXT, regime_score REAL,
          geo_status TEXT, geo_score REAL, social_source TEXT, social_status TEXT,
          spy_gap REAL, qqq_gap REAL, xlf_gap REAL, fas_gap REAL, faz_gap REAL,
          vix_level REAL, vix_15m REAL, reasons_json TEXT);
        CREATE TABLE IF NOT EXISTS premarket_symbols(
          id TEXT PRIMARY KEY, intelligence_id TEXT, ts TEXT, session_date TEXT,
          symbol TEXT, latest_price REAL, prior_close REAL, gap_pct REAL,
          premarket_change_pct REAL, momentum_5m REAL, momentum_15m REAL,
          premarket_volume REAL, bar_count INTEGER);
        """)


def _audit_gate_reason(message, attempted=False, accepted=False):
    if accepted:
        return "ORDER_ACCEPTED"
    text = str(message or "").strip().lower()
    if "max open positions" in text:
        return "MAX_OPEN_POSITIONS"
    if "portfolio exposure limit" in text:
        return "PORTFOLIO_EXPOSURE_LIMIT"
    if "daily trade limit" in text:
        return "DAILY_TRADE_LIMIT"
    if "daily realized loss limit" in text:
        return "DAILY_REALIZED_LOSS_LIMIT"
    if "market closed" in text:
        return "MARKET_CLOSED"
    if attempted:
        return "ORDER_SUBMIT_FAILED"
    return "NOT_ATTEMPTED"


def _order_was_attempted(message):
    text = str(message or "").strip().lower()
    return text not in {
        "max open positions",
        "portfolio exposure limit",
        "daily trade limit",
        "daily realized loss limit",
        "market closed",
    }


def latest_order_id(symbol, side):
    try:
        with db_connect() as conn:
            row = conn.execute(
                "SELECT alpaca_order_id FROM orders WHERE symbol=? AND side=? ORDER BY ts DESC LIMIT 1",
                (symbol, side.lower()),
            ).fetchone()
        return str(row["alpaca_order_id"]) if row and row["alpaca_order_id"] else ""
    except Exception:
        return ""


def log_decision_funnel(
    *,
    event_id,
    symbol,
    side,
    score,
    threshold,
    raw_threshold_cross,
    confirmation_count,
    confirmation_required,
    position_state,
    projected_exposure,
    open_position_count,
    market_open,
    model_decision,
    final_disposition,
    gate_reason,
    decision_reason,
):
    row = {
        "event_id": event_id,
        "ts": utc_now().isoformat(),
        "symbol": symbol,
        "side": side,
        "score": score,
        "threshold": threshold,
        "raw_threshold_cross": int(bool(raw_threshold_cross)),
        "confirmation_count": int(confirmation_count),
        "confirmation_required": int(confirmation_required),
        "position_state": position_state,
        "projected_exposure": float(projected_exposure),
        "open_position_count": int(open_position_count),
        "market_open": int(bool(market_open)),
        "model_decision": model_decision,
        "final_disposition": final_disposition,
        "gate_reason": gate_reason,
        "decision_reason": decision_reason,
    }
    with db_connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO decision_funnel(
               event_id,ts,symbol,side,score,threshold,raw_threshold_cross,
               confirmation_count,confirmation_required,position_state,
               projected_exposure,open_position_count,market_open,model_decision,
               final_disposition,gate_reason,decision_reason
            ) VALUES(
               :event_id,:ts,:symbol,:side,:score,:threshold,:raw_threshold_cross,
               :confirmation_count,:confirmation_required,:position_state,
               :projected_exposure,:open_position_count,:market_open,:model_decision,
               :final_disposition,:gate_reason,:decision_reason
            )""",
            row,
        )
    append_csv(daily_paths()["decision_funnel"], row)


def log_order_attempt(
    *,
    decision_event_id,
    symbol,
    side,
    attempted,
    accepted,
    gate_reason,
    alpaca_order_id="",
):
    row = {
        "attempt_id": str(uuid.uuid4()),
        "ts": utc_now().isoformat(),
        "decision_event_id": decision_event_id,
        "symbol": symbol,
        "side": side,
        "attempted": int(bool(attempted)),
        "accepted": int(bool(accepted)),
        "gate_reason": gate_reason,
        "alpaca_order_id": alpaca_order_id or "",
    }
    with db_connect() as conn:
        conn.execute(
            """INSERT INTO order_attempts(
               attempt_id,ts,decision_event_id,symbol,side,attempted,accepted,
               gate_reason,alpaca_order_id
            ) VALUES(
               :attempt_id,:ts,:decision_event_id,:symbol,:side,:attempted,:accepted,
               :gate_reason,:alpaca_order_id
            )""",
            row,
        )
    append_csv(daily_paths()["order_attempts"], row)


def funnel_context(symbol, score, decision, positions, market_open):
    position = positions.get(symbol)
    exposure = sum(p["market_value"] for p in positions.values())
    has_position = bool(position)
    raw_buy_cross = (not has_position) and score >= BUY_SCORE_THRESHOLD
    raw_sell_cross = has_position and score <= SELL_SCORE_THRESHOLD

    if decision == "SELL" or raw_sell_cross:
        side = "SELL"
        threshold = SELL_SCORE_THRESHOLD
        raw_cross = raw_sell_cross
        confirmation_required = SELL_CONFIRMATIONS
        confirmation_count = SELL_CONFIRMATIONS if decision == "SELL" and raw_sell_cross else sell_counts.get(symbol, 0)
        projected_exposure = max(0.0, exposure - float((position or {}).get("market_value", 0.0)))
    elif decision == "BUY" or raw_buy_cross:
        side = "BUY"
        threshold = BUY_SCORE_THRESHOLD
        raw_cross = raw_buy_cross
        confirmation_required = BUY_CONFIRMATIONS
        confirmation_count = BUY_CONFIRMATIONS if decision == "BUY" and raw_buy_cross else buy_counts.get(symbol, 0)
        room = max(0.0, MAX_TOTAL_EXPOSURE - exposure)
        proposed_notional = min(MAX_TRADE_DOLLARS, room)
        projected_exposure = exposure + max(0.0, proposed_notional)
    else:
        return None

    return {
        "event_id": str(uuid.uuid4()),
        "symbol": symbol,
        "side": side,
        "score": score,
        "threshold": threshold,
        "raw_threshold_cross": raw_cross,
        "confirmation_count": confirmation_count,
        "confirmation_required": confirmation_required,
        "position_state": "HAS_POSITION" if has_position else "NO_POSITION",
        "projected_exposure": projected_exposure,
        "open_position_count": len(positions),
        "market_open": market_open,
        "model_decision": decision,
    }


# ---------------- Market data ----------------
def get_recent_bars(symbol, minutes=90):
    end = utc_now(); start = end - timedelta(minutes=minutes + 20)
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, start=start, end=end, limit=minutes+20, feed=ALPACA_DATA_FEED)
    bars = data_client.get_stock_bars(req)
    return list(bars[symbol]) if symbol in bars.data else []

def snapshot(symbol):
    bars = get_recent_bars(symbol)
    if len(bars) < 21: raise RuntimeError(f"Not enough bars for {symbol}: {len(bars)}")
    closes = [float(x.close) for x in bars]; vols = [float(x.volume) for x in bars]
    price = closes[-1]; s20 = sma(closes,20)
    avg_vol = sum(vols[-21:-1])/20 if len(vols)>=21 else max(vols[-1],1)
    return {
        "symbol":symbol, "price":price, "sma20":s20,
        "momentum_5m":pct_change(price,closes[-6]) if len(closes)>=6 else 0,
        "momentum_15m":pct_change(price,closes[-16]) if len(closes)>=16 else 0,
        "rsi14":rsi(closes,14), "volume_ratio": vols[-1]/avg_vol if avg_vol else 1.0,
    }

def fetch_vix():
    """Actual ^VIX from Yahoo chart endpoint; fallback to VIXY ETF if unavailable."""
    try:
        u="https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1m&range=1d"
        j=requests.get(u,headers={"User-Agent":"Mozilla/5.0"},timeout=8).json()
        r=j["chart"]["result"][0]; closes=[x for x in r["indicators"]["quote"][0]["close"] if x is not None]
        if len(closes)>=16:
            p=float(closes[-1]); return {"level":p,"change_5m":pct_change(p,float(closes[-6])),"change_15m":pct_change(p,float(closes[-16])),"source":"^VIX"}
    except Exception as e:
        log.warning("^VIX fetch failed (%s); using %s proxy",e,VIX_FALLBACK_SYMBOL)
    try:
        s=snapshot(VIX_FALLBACK_SYMBOL)
        return {"level":None,"change_5m":s["momentum_5m"],"change_15m":s["momentum_15m"],"source":VIX_FALLBACK_SYMBOL}
    except Exception:
        return {"level":None,"change_5m":0.0,"change_15m":0.0,"source":"unavailable"}


def get_daily_trend(symbol):
    end = utc_now()
    start = end - timedelta(days=430)
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        limit=320,
        feed=ALPACA_DATA_FEED,
    )
    bars = data_client.get_stock_bars(req)
    rows = list(bars[symbol]) if symbol in bars.data else []
    closes = [float(x.close) for x in rows]
    if len(closes) < 200:
        raise RuntimeError(f"Not enough daily bars for regime {symbol}: {len(closes)}")
    close = closes[-1]
    return {
        "close": close,
        "sma50": sum(closes[-50:]) / 50.0,
        "sma200": sum(closes[-200:]) / 200.0,
        "mom20": pct_change(close, closes[-21]) if len(closes) >= 21 else 0.0,
    }


def cached_regime_trends():
    now = time.time()
    cached = _REGIME_TREND_CACHE.get("value")
    age = now - float(_REGIME_TREND_CACHE.get("fetched_at") or 0.0)
    if cached is not None and age < REGIME_TREND_CACHE_SECONDS:
        return cached
    try:
        value = {"SPY": get_daily_trend("SPY"), "QQQ": get_daily_trend("QQQ")}
        _REGIME_TREND_CACHE["value"] = value
        _REGIME_TREND_CACHE["fetched_at"] = now
        return value
    except Exception as exc:
        log.warning("Regime daily trend refresh failed: %s", exc)
        return cached


def market_regime_shadow(vix):
    if not REGIME_SHADOW_ENABLED:
        return {"state":"DISABLED","score":None,"reasons":[],"defensive_asset":REGIME_SHADOW_DEFENSIVE_ASSET}
    trends = cached_regime_trends()
    if not trends or "SPY" not in trends or "QQQ" not in trends:
        return {"state":"UNKNOWN","score":None,"reasons":["DAILY_TREND_UNAVAILABLE"],"defensive_asset":REGIME_SHADOW_DEFENSIVE_ASSET}

    spy = trends["SPY"]; qqq = trends["QQQ"]
    score = 0.0
    reasons = []

    if spy["close"] > spy["sma200"] * (1.0 + REGIME_SPY_200_BUFFER_PCT):
        score += 25; reasons.append("SPY_ABOVE_200_BUFFER")
    else:
        reasons.append("SPY_NOT_ABOVE_200_BUFFER")
    if spy["close"] > spy["sma50"]:
        score += 15; reasons.append("SPY_ABOVE_50")
    else:
        reasons.append("SPY_NOT_ABOVE_50")
    if spy["sma50"] > spy["sma200"]:
        score += 15; reasons.append("SPY_50_ABOVE_200")
    else:
        reasons.append("SPY_50_NOT_ABOVE_200")
    if qqq["close"] > qqq["sma200"] * (1.0 + REGIME_QQQ_200_BUFFER_PCT):
        score += 15; reasons.append("QQQ_ABOVE_200_BUFFER")
    else:
        reasons.append("QQQ_NOT_ABOVE_200_BUFFER")
    if spy["mom20"] > 0:
        score += 15; reasons.append("SPY_MOM20_POSITIVE")
    else:
        reasons.append("SPY_MOM20_NONPOSITIVE")

    vix_level = vix.get("level")
    if vix_level is not None and float(vix_level) < REGIME_VIX_MAX_RISK_ON:
        score += 15; reasons.append("VIX_BELOW_STRESS")
    elif vix_level is None:
        reasons.append("VIX_LEVEL_UNAVAILABLE")
    else:
        reasons.append("VIX_AT_OR_ABOVE_STRESS")

    if score >= REGIME_RISK_ON_MIN:
        state = "RISK_ON"
    elif score >= REGIME_NEUTRAL_MIN:
        state = "NEUTRAL"
    else:
        state = "RISK_OFF"

    return {
        "state": state,
        "score": score,
        "spy_close": spy["close"],
        "spy_sma50": spy["sma50"],
        "spy_sma200": spy["sma200"],
        "spy_mom20": spy["mom20"],
        "qqq_close": qqq["close"],
        "qqq_sma200": qqq["sma200"],
        "vix_level": vix_level,
        "defensive_asset": REGIME_SHADOW_DEFENSIVE_ASSET,
        "reasons": reasons,
    }


def regime_shadow_action(regime):
    state = str((regime or {}).get("state") or "UNKNOWN")
    if state == "RISK_ON":
        return "ALLOW_EQUITY"
    if state == "NEUTRAL":
        return "REDUCE_EQUITY_EXPOSURE"
    if state == "RISK_OFF":
        return "PREFER_DEFENSIVE_ASSET"
    return "NO_SHADOW_ACTION"


def maybe_log_market_regime(regime):
    if not REGIME_SHADOW_ENABLED:
        return
    now = time.time()
    state = str((regime or {}).get("state") or "UNKNOWN")
    if (
        state == _LAST_REGIME_LOG.get("state")
        and now - float(_LAST_REGIME_LOG.get("ts") or 0.0) < REGIME_SHADOW_LOG_INTERVAL_SECONDS
    ):
        return
    row = {
        "id": str(uuid.uuid4()),
        "ts": utc_now().isoformat(),
        "regime_state": state,
        "regime_score": regime.get("score"),
        "spy_close": regime.get("spy_close"),
        "spy_sma50": regime.get("spy_sma50"),
        "spy_sma200": regime.get("spy_sma200"),
        "spy_mom20": regime.get("spy_mom20"),
        "qqq_close": regime.get("qqq_close"),
        "qqq_sma200": regime.get("qqq_sma200"),
        "vix_level": regime.get("vix_level"),
        "defensive_asset": regime.get("defensive_asset"),
        "reasons_json": json.dumps(regime.get("reasons") or []),
    }
    with db_connect() as conn:
        conn.execute(
            """INSERT INTO market_regime_shadow(
               id,ts,regime_state,regime_score,spy_close,spy_sma50,spy_sma200,
               spy_mom20,qqq_close,qqq_sma200,vix_level,defensive_asset,reasons_json
            ) VALUES(
               :id,:ts,:regime_state,:regime_score,:spy_close,:spy_sma50,:spy_sma200,
               :spy_mom20,:qqq_close,:qqq_sma200,:vix_level,:defensive_asset,:reasons_json
            )""",
            row,
        )
    append_csv(daily_paths()["market_regime_shadow"], row)
    _LAST_REGIME_LOG["ts"] = now
    _LAST_REGIME_LOG["state"] = state


def log_regime_decision_shadow(decision_event_id, rec, regime):
    if not REGIME_SHADOW_ENABLED:
        return
    row = {
        "id": str(uuid.uuid4()),
        "ts": utc_now().isoformat(),
        "decision_event_id": decision_event_id or "",
        "symbol": rec["symbol"],
        "model_decision": rec["decision"],
        "score": rec["score"],
        "regime_state": regime.get("state"),
        "regime_score": regime.get("score"),
        "shadow_action": regime_shadow_action(regime),
        "defensive_asset": regime.get("defensive_asset"),
    }
    with db_connect() as conn:
        conn.execute(
            """INSERT INTO regime_decision_shadow(
               id,ts,decision_event_id,symbol,model_decision,score,regime_state,regime_score,
               shadow_action,defensive_asset
            ) VALUES(
               :id,:ts,:decision_event_id,:symbol,:model_decision,:score,:regime_state,:regime_score,
               :shadow_action,:defensive_asset
            )""",
            row,
        )
    append_csv(daily_paths()["regime_decision_shadow"], row)


def financial_leverage_shadow(snaps, regime, vix):
    if not FIN_LEVERAGE_SHADOW_ENABLED:
        return {"candidate":"NONE","score":0.0,"reasons":["DISABLED"]}
    if any(sym not in snaps for sym in SHADOW_FINANCIAL_SYMBOLS):
        return {"candidate":"NONE","score":0.0,"reasons":["FINANCIAL_SNAPSHOT_UNAVAILABLE"]}

    xlf = snaps["XLF"]; fas = snaps["FAS"]; faz = snaps["FAZ"]
    state = str((regime or {}).get("state") or "UNKNOWN")
    vix_level = vix.get("level")
    vix15 = float(vix.get("change_15m", 0.0) or 0.0)

    bull = 0.0; bull_reasons = []
    bear = 0.0; bear_reasons = []

    if state == "RISK_ON":
        bull += 25; bull_reasons.append("REGIME_RISK_ON")
    elif state == "RISK_OFF":
        bear += 25; bear_reasons.append("REGIME_RISK_OFF")

    if xlf["momentum_5m"] > 0:
        bull += 15; bull_reasons.append("XLF_5M_UP")
    elif xlf["momentum_5m"] < 0:
        bear += 15; bear_reasons.append("XLF_5M_DOWN")
    if xlf["momentum_15m"] > 0:
        bull += 20; bull_reasons.append("XLF_15M_UP")
    elif xlf["momentum_15m"] < 0:
        bear += 20; bear_reasons.append("XLF_15M_DOWN")

    if fas["momentum_5m"] > 0:
        bull += 10; bull_reasons.append("FAS_5M_UP")
    if fas["momentum_15m"] > 0:
        bull += 10; bull_reasons.append("FAS_15M_UP")
    if faz["momentum_5m"] < 0:
        bull += 10; bull_reasons.append("FAZ_5M_DOWN")
    if faz["momentum_5m"] > 0:
        bear += 10; bear_reasons.append("FAZ_5M_UP")
    if faz["momentum_15m"] > 0:
        bear += 10; bear_reasons.append("FAZ_15M_UP")
    if fas["momentum_5m"] < 0:
        bear += 10; bear_reasons.append("FAS_5M_DOWN")

    if vix_level is not None and float(vix_level) < REGIME_VIX_MAX_RISK_ON:
        bull += 10; bull_reasons.append("VIX_NOT_STRESSED")
    if (vix_level is not None and float(vix_level) >= REGIME_VIX_MAX_RISK_ON) or vix15 > 0.03:
        bear += 10; bear_reasons.append("VIX_STRESS_OR_RISING")

    if bull >= FIN_LEVERAGE_MIN_SCORE and bull > bear:
        candidate = "FAS"; score = bull; reasons = bull_reasons
    elif bear >= FIN_LEVERAGE_MIN_SCORE and bear > bull:
        candidate = "FAZ"; score = bear; reasons = bear_reasons
    else:
        candidate = "NONE"; score = max(bull, bear); reasons = ["NO_HIGH_CONVICTION_DIRECTION"]

    return {
        "candidate": candidate,
        "score": score,
        "bull_score": bull,
        "bear_score": bear,
        "reasons": reasons,
        "xlf": xlf, "fas": fas, "faz": faz,
        "regime_state": state,
        "regime_score": regime.get("score"),
        "vix_level": vix_level,
        "vix_15m": vix15,
    }


def maybe_log_financial_leverage_shadow(fin):
    if not FIN_LEVERAGE_SHADOW_ENABLED:
        return
    if not all(k in fin for k in ("xlf","fas","faz")):
        return
    now = time.time()
    if now - float(_LAST_FIN_LEVERAGE_LOG.get("ts") or 0.0) < FIN_LEVERAGE_SNAPSHOT_SECONDS:
        return
    row = {
        "id": str(uuid.uuid4()),
        "ts": utc_now().isoformat(),
        "regime_state": fin.get("regime_state"),
        "regime_score": fin.get("regime_score"),
        "candidate": fin.get("candidate"),
        "candidate_score": fin.get("score"),
        "xlf_price": fin["xlf"]["price"],
        "xlf_mom5": fin["xlf"]["momentum_5m"],
        "xlf_mom15": fin["xlf"]["momentum_15m"],
        "fas_price": fin["fas"]["price"],
        "fas_mom5": fin["fas"]["momentum_5m"],
        "fas_mom15": fin["fas"]["momentum_15m"],
        "faz_price": fin["faz"]["price"],
        "faz_mom5": fin["faz"]["momentum_5m"],
        "faz_mom15": fin["faz"]["momentum_15m"],
        "vix_level": fin.get("vix_level"),
        "vix_15m": fin.get("vix_15m"),
        "reasons_json": json.dumps(fin.get("reasons") or []),
    }
    with db_connect() as conn:
        conn.execute(
            """INSERT INTO financial_leverage_shadow(
               id,ts,regime_state,regime_score,candidate,candidate_score,
               xlf_price,xlf_mom5,xlf_mom15,fas_price,fas_mom5,fas_mom15,
               faz_price,faz_mom5,faz_mom15,vix_level,vix_15m,reasons_json
            ) VALUES(
               :id,:ts,:regime_state,:regime_score,:candidate,:candidate_score,
               :xlf_price,:xlf_mom5,:xlf_mom15,:fas_price,:fas_mom5,:fas_mom15,
               :faz_price,:faz_mom5,:faz_mom15,:vix_level,:vix_15m,:reasons_json
            )""", row)
    append_csv(daily_paths()["financial_leverage_shadow"], row)
    _LAST_FIN_LEVERAGE_LOG["ts"] = now


def maybe_log_financial_leverage_signal(fin):
    candidate = str(fin.get("candidate") or "NONE")
    if candidate not in {"FAS","FAZ"} or not all(k in fin for k in ("xlf","fas","faz")):
        return None
    now = time.time()
    same = candidate == _LAST_FIN_LEVERAGE_SIGNAL.get("candidate")
    if same and now - float(_LAST_FIN_LEVERAGE_SIGNAL.get("ts") or 0.0) < FIN_LEVERAGE_SIGNAL_COOLDOWN_SECONDS:
        return None
    row = {
        "signal_id": str(uuid.uuid4()),
        "ts": utc_now().isoformat(),
        "candidate": candidate,
        "candidate_score": fin.get("score"),
        "regime_state": fin.get("regime_state"),
        "regime_score": fin.get("regime_score"),
        "xlf_price": fin["xlf"]["price"],
        "fas_price": fin["fas"]["price"],
        "faz_price": fin["faz"]["price"],
        "vix_level": fin.get("vix_level"),
        "reasons_json": json.dumps(fin.get("reasons") or []),
    }
    with db_connect() as conn:
        conn.execute(
            """INSERT INTO financial_leverage_signals(
               signal_id,ts,candidate,candidate_score,regime_state,regime_score,
               xlf_price,fas_price,faz_price,vix_level,reasons_json
            ) VALUES(
               :signal_id,:ts,:candidate,:candidate_score,:regime_state,:regime_score,
               :xlf_price,:fas_price,:faz_price,:vix_level,:reasons_json
            )""", row)
    append_csv(daily_paths()["financial_leverage_signals"], row)
    _LAST_FIN_LEVERAGE_SIGNAL["ts"] = now
    _LAST_FIN_LEVERAGE_SIGNAL["candidate"] = candidate
    return row["signal_id"]


def capture_financial_leverage_outcomes(fin):
    if not FIN_LEVERAGE_SHADOW_ENABLED or not all(k in fin for k in ("xlf","fas","faz")):
        return
    cutoff = (utc_now() - timedelta(minutes=max(FIN_LEVERAGE_OUTCOME_HORIZONS or (60,)) + 15)).isoformat()
    with db_connect() as conn:
        signals = [dict(r) for r in conn.execute(
            "SELECT * FROM financial_leverage_signals WHERE ts>=? ORDER BY ts", (cutoff,)
        )]
        for sig in signals:
            try:
                sig_ts = datetime.fromisoformat(str(sig["ts"]).replace("Z","+00:00"))
            except Exception:
                continue
            age_minutes = (utc_now() - sig_ts.astimezone(timezone.utc)).total_seconds() / 60.0
            for horizon in FIN_LEVERAGE_OUTCOME_HORIZONS:
                if age_minutes < horizon:
                    continue
                exists = conn.execute(
                    "SELECT 1 FROM financial_leverage_outcomes WHERE signal_id=? AND horizon_minutes=?",
                    (sig["signal_id"], int(horizon)),
                ).fetchone()
                if exists:
                    continue
                fas_ret = pct_change(fin["fas"]["price"], float(sig["fas_price"]))
                faz_ret = pct_change(fin["faz"]["price"], float(sig["faz_price"]))
                xlf_ret = pct_change(fin["xlf"]["price"], float(sig["xlf_price"]))
                candidate_ret = fas_ret if sig["candidate"] == "FAS" else faz_ret
                row = {
                    "id": str(uuid.uuid4()),
                    "signal_id": sig["signal_id"],
                    "observed_at": utc_now().isoformat(),
                    "horizon_minutes": int(horizon),
                    "candidate": sig["candidate"],
                    "candidate_return": candidate_ret,
                    "xlf_return": xlf_ret,
                    "fas_return": fas_ret,
                    "faz_return": faz_ret,
                }
                conn.execute(
                    """INSERT INTO financial_leverage_outcomes(
                       id,signal_id,observed_at,horizon_minutes,candidate,candidate_return,
                       xlf_return,fas_return,faz_return
                    ) VALUES(
                       :id,:signal_id,:observed_at,:horizon_minutes,:candidate,:candidate_return,
                       :xlf_return,:fas_return,:faz_return
                    )""", row)
                append_csv(daily_paths()["financial_leverage_outcomes"], row)


def _aware_utc(dt):
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _session_date(next_open):
    return _aware_utc(next_open).astimezone(MARKET_TZ).date().isoformat()


def _prior_close(symbol, before_dt):
    try:
        end = _aware_utc(before_dt)
        start = end - timedelta(days=14)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            limit=10,
            feed=ALPACA_DATA_FEED,
        )
        bars = data_client.get_stock_bars(req)
        rows = list(bars[symbol]) if symbol in bars.data else []
        return float(rows[-1].close) if rows else None
    except Exception:
        return None


def premarket_symbol_snapshot(symbol, next_open):
    next_open_utc = _aware_utc(next_open)
    open_et = next_open_utc.astimezone(MARKET_TZ)
    session_start_et = open_et.replace(hour=4, minute=0, second=0, microsecond=0)
    start = session_start_et.astimezone(timezone.utc)
    end = min(utc_now(), next_open_utc)
    prior = _prior_close(symbol, start)
    try:
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            limit=2000,
            feed=ALPACA_DATA_FEED,
        )
        bars = data_client.get_stock_bars(req)
        rows = list(bars[symbol]) if symbol in bars.data else []
    except Exception:
        rows = []

    closes = [float(x.close) for x in rows]
    vols = [float(x.volume or 0) for x in rows]
    latest = closes[-1] if closes else None
    first = closes[0] if closes else None
    return {
        "symbol": symbol,
        "latest_price": latest,
        "prior_close": prior,
        "gap_pct": pct_change(latest, prior) if latest is not None and prior else None,
        "premarket_change_pct": pct_change(latest, first) if latest is not None and first else None,
        "momentum_5m": pct_change(latest, closes[-6]) if len(closes) >= 6 else 0.0,
        "momentum_15m": pct_change(latest, closes[-16]) if len(closes) >= 16 else 0.0,
        "premarket_volume": sum(vols),
        "bar_count": len(rows),
    }


def premarket_bias_from(symbols, vix):
    score = 50.0
    reasons = []

    def gap(sym):
        v = (symbols.get(sym) or {}).get("gap_pct")
        return float(v) if v is not None else None

    spy_gap = gap("SPY")
    qqq_gap = gap("QQQ")
    xlf_gap = gap("XLF")

    for label, value, weight in (("SPY", spy_gap, 15), ("QQQ", qqq_gap, 10), ("XLF", xlf_gap, 10)):
        if value is None:
            reasons.append(f"{label}_GAP_UNAVAILABLE")
        elif value >= 0.0025:
            score += weight; reasons.append(f"{label}_GAP_POSITIVE")
        elif value <= -0.0025:
            score -= weight; reasons.append(f"{label}_GAP_NEGATIVE")
        else:
            reasons.append(f"{label}_GAP_FLAT")

    spy_move = (symbols.get("SPY") or {}).get("premarket_change_pct")
    if spy_move is not None:
        if float(spy_move) >= 0.002:
            score += 10; reasons.append("SPY_PREMARKET_TREND_UP")
        elif float(spy_move) <= -0.002:
            score -= 10; reasons.append("SPY_PREMARKET_TREND_DOWN")

    vix15 = float(vix.get("change_15m", 0.0) or 0.0)
    if vix15 >= 0.03:
        score -= 10; reasons.append("VIX_RISING")
    elif vix15 <= -0.03:
        score += 10; reasons.append("VIX_FALLING")

    score = clamp(score, 0.0, 100.0)
    bias = "BULLISH" if score >= 65 else ("BEARISH" if score <= 35 else "NEUTRAL")
    return bias, score, reasons


def load_latest_premarket_context(session_date=None):
    global _PREMARKET_CONTEXT
    try:
        with db_connect() as conn:
            if session_date:
                row = conn.execute(
                    "SELECT * FROM premarket_intelligence WHERE session_date=? ORDER BY ts DESC LIMIT 1",
                    (session_date,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM premarket_intelligence ORDER BY ts DESC LIMIT 1"
                ).fetchone()
        if row:
            data = dict(row)
            _PREMARKET_CONTEXT = {
                "session_date": data.get("session_date"),
                "bias": data.get("bias") or "UNAVAILABLE",
                "bias_score": float(data.get("bias_score") or 50.0),
                "generated_at": data.get("ts"),
                "status": "AVAILABLE",
                "regime_state": data.get("regime_state"),
                "geo_status": data.get("geo_status"),
                "social_status": data.get("social_status"),
            }
    except Exception:
        pass
    return _PREMARKET_CONTEXT


def premarket_context_adjustment(symbol):
    ctx = _PREMARKET_CONTEXT
    if not PREMARKET_ENABLED or ctx.get("status") != "AVAILABLE":
        return 0.0
    now_et = market_now()
    if ctx.get("session_date") != now_et.date().isoformat():
        return 0.0
    open_et = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    elapsed = (now_et - open_et).total_seconds() / 60.0
    if elapsed < 0 or elapsed > PREMARKET_CONTEXT_ACTIVE_MINUTES:
        return 0.0

    bias = str(ctx.get("bias") or "NEUTRAL")
    raw = PREMARKET_CONTEXT_MAX_ADJ if bias == "BULLISH" else (-PREMARKET_CONTEXT_MAX_ADJ if bias == "BEARISH" else 0.0)
    if symbol == "GLD":
        raw *= -0.5
    return clamp(raw, -PREMARKET_CONTEXT_MAX_ADJ, PREMARKET_CONTEXT_MAX_ADJ)


def premarket_completed_offsets(session_date):
    try:
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT scheduled_offset_minutes FROM premarket_intelligence WHERE session_date=?",
                (session_date,),
            ).fetchall()
        return {int(r[0]) for r in rows}
    except Exception:
        return set()


def run_premarket_assessment(clock, scheduled_offset):
    global _PREMARKET_CONTEXT
    next_open = _aware_utc(clock.next_open)
    session_date = _session_date(next_open)
    symbols = {}
    for sym in ("SPY","QQQ","XLF","FAS","FAZ"):
        symbols[sym] = premarket_symbol_snapshot(sym, next_open)

    vix = fetch_vix()
    geo = geo_snapshot()
    regime = market_regime_shadow(vix)
    bias, bias_score, reasons = premarket_bias_from(symbols, vix)
    intel_id = f"{session_date}:{int(scheduled_offset)}"

    row = {
        "id": intel_id,
        "session_date": session_date,
        "scheduled_offset_minutes": int(scheduled_offset),
        "ts": utc_now().isoformat(),
        "bias": bias,
        "bias_score": bias_score,
        "regime_state": regime.get("state"),
        "regime_score": regime.get("score"),
        "geo_status": geo.get("status"),
        "geo_score": geo.get("score_adjustment"),
        "social_source": PREMARKET_SOCIAL_SOURCE,
        "social_status": "UNAVAILABLE" if PREMARKET_SOCIAL_SOURCE.upper() == "UNAVAILABLE" else "CONFIGURED",
        "spy_gap": (symbols["SPY"] or {}).get("gap_pct"),
        "qqq_gap": (symbols["QQQ"] or {}).get("gap_pct"),
        "xlf_gap": (symbols["XLF"] or {}).get("gap_pct"),
        "fas_gap": (symbols["FAS"] or {}).get("gap_pct"),
        "faz_gap": (symbols["FAZ"] or {}).get("gap_pct"),
        "vix_level": vix.get("level"),
        "vix_15m": vix.get("change_15m"),
        "reasons_json": json.dumps(reasons),
    }
    with db_connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO premarket_intelligence(
               id,session_date,scheduled_offset_minutes,ts,bias,bias_score,regime_state,regime_score,
               geo_status,geo_score,social_source,social_status,spy_gap,qqq_gap,xlf_gap,fas_gap,faz_gap,
               vix_level,vix_15m,reasons_json
            ) VALUES(
               :id,:session_date,:scheduled_offset_minutes,:ts,:bias,:bias_score,:regime_state,:regime_score,
               :geo_status,:geo_score,:social_source,:social_status,:spy_gap,:qqq_gap,:xlf_gap,:fas_gap,:faz_gap,
               :vix_level,:vix_15m,:reasons_json
            )""",
            row,
        )
        for sym, snap in symbols.items():
            srow = {
                "id": f"{intel_id}:{sym}",
                "intelligence_id": intel_id,
                "ts": row["ts"],
                "session_date": session_date,
                **snap,
            }
            conn.execute(
                """INSERT OR REPLACE INTO premarket_symbols(
                   id,intelligence_id,ts,session_date,symbol,latest_price,prior_close,gap_pct,
                   premarket_change_pct,momentum_5m,momentum_15m,premarket_volume,bar_count
                ) VALUES(
                   :id,:intelligence_id,:ts,:session_date,:symbol,:latest_price,:prior_close,:gap_pct,
                   :premarket_change_pct,:momentum_5m,:momentum_15m,:premarket_volume,:bar_count
                )""",
                srow,
            )
            append_csv(daily_paths()["premarket_symbols"], srow)
    append_csv(daily_paths()["premarket_intelligence"], row)

    _PREMARKET_CONTEXT = {
        "session_date": session_date,
        "bias": bias,
        "bias_score": bias_score,
        "generated_at": row["ts"],
        "status": "AVAILABLE",
        "regime_state": regime.get("state"),
        "geo_status": geo.get("status"),
        "social_status": row["social_status"],
    }
    tmp = PREMARKET_STATE_PATH.with_suffix(PREMARKET_STATE_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps({"intelligence": row, "symbols": symbols}, indent=2), encoding="utf-8")
    tmp.replace(PREMARKET_STATE_PATH)

    def fmt_gap(sym):
        g = (symbols.get(sym) or {}).get("gap_pct")
        return "n/a" if g is None else f"{float(g)*100:+.2f}%"

    log.info(
        "PREMARKET %dm | bias=%s %.0f | SPY %s | QQQ %s | XLF %s | FAS %s | FAZ %s | geo=%s | social=%s",
        int(scheduled_offset), bias, bias_score,
        fmt_gap("SPY"), fmt_gap("QQQ"), fmt_gap("XLF"), fmt_gap("FAS"), fmt_gap("FAZ"),
        geo.get("status"), row["social_status"],
    )
    return row


def maybe_run_premarket(clock):
    if not PREMARKET_ENABLED:
        return None
    next_open = _aware_utc(clock.next_open)
    now = utc_now()
    session_date = _session_date(next_open)
    completed = premarket_completed_offsets(session_date)
    eligible = []
    for offset in PREMARKET_REFRESH_OFFSETS:
        due = next_open - timedelta(minutes=int(offset))
        if due <= now < next_open and int(offset) not in completed:
            eligible.append(int(offset))
    if not eligible:
        return None
    # If the process started late, run only the most recent missed slot, not a burst of stale slots.
    chosen = min(eligible)
    return run_premarket_assessment(clock, chosen)


def next_premarket_due(clock):
    if not PREMARKET_ENABLED:
        return _aware_utc(clock.next_open)
    next_open = _aware_utc(clock.next_open)
    now = utc_now()
    session_date = _session_date(next_open)
    completed = premarket_completed_offsets(session_date)
    candidates = []
    for offset in PREMARKET_REFRESH_OFFSETS:
        due = next_open - timedelta(minutes=int(offset))
        if due > now and int(offset) not in completed:
            candidates.append(due)
    candidates.append(next_open)
    return min(candidates)


def eod_due_target(now_et):
    if now_et.weekday() >= 5:
        return None
    state = load_stock_eod_state()
    if state.get("last_sent_date") == now_et.date().isoformat():
        return None
    target = now_et.replace(
        hour=PUSHOVER_STOCK_EOD_HOUR,
        minute=PUSHOVER_STOCK_EOD_MINUTE,
        second=0,
        microsecond=0,
    )
    close_floor = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    if now_et < close_floor:
        return None
    return target if now_et < target else now_et


def sleep_until(target_utc, reason):
    global _LAST_IDLE_TARGET
    target_utc = _aware_utc(target_utc)
    seconds = max(1.0, (target_utc - utc_now()).total_seconds())
    log_key = (reason, target_utc.isoformat(timespec="minutes"))
    if log_key != _LAST_IDLE_TARGET:
        log.info("%s | next wake %s ET", reason, target_utc.astimezone(MARKET_TZ).strftime("%Y-%m-%d %H:%M"))
        _LAST_IDLE_TARGET = log_key
    time.sleep(min(seconds, max(60, CLOSED_IDLE_MAX_SLEEP_SECONDS)))


def market_warmup_remaining_minutes():
    now_et = market_now()
    open_et = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    elapsed = (now_et - open_et).total_seconds() / 60.0
    return max(0.0, MARKET_OPEN_WARMUP_MINUTES - elapsed)


# ---------------- Scoring ----------------
def technical_score(s):
    score=50.0
    if s["sma20"]:
        dist=pct_change(s["price"],s["sma20"]); score += clamp(dist/0.01*10,-10,10)
    score += clamp(s["momentum_5m"]/0.01*8,-8,8)
    score += clamp(s["momentum_15m"]/0.02*12,-12,12)
    direction = 1 if s["momentum_5m"]>=0 else -1
    score += direction*clamp(max(s["volume_ratio"]-1,0)*4,0,6)
    rv=s["rsi14"]
    if rv>50: score += clamp((rv-50)/20*5,0,5)
    elif rv<50: score -= clamp((50-rv)/20*5,0,5)
    return clamp(score,0,100)

def vix_adjustment(symbol,v):
    """VIX is regime context only; effect varies by asset."""
    level=v.get("level"); c5=v.get("change_5m",0); c15=v.get("change_15m",0)
    # stress: level + acceleration. If only VIXY is available, change still contributes.
    stress=0.0
    if level is not None:
        if level < 15: stress=-1
        elif level < 20: stress=0
        elif level < 25: stress=1.5
        elif level < 30: stress=3
        else: stress=5
    stress += clamp(c5/0.05*2,-2,2) + clamp(c15/0.10*2,-2,2)
    beta={"NVDA":1.0,"TSLA":1.0,"QQQ":0.85,"AAPL":0.75,"AMZN":0.8,"SPY":0.6,"WMT":0.3,"XOM":0.25,"GLD":-0.35}.get(symbol,0.5)
    return clamp(-stress*beta,-10,6)

def geo_snapshot():
    base={"score_adjustment":0.0,"status":"missing","active_event_count":0}
    if not GEO_FEED_PATH.exists(): return base
    try:
        j=json.loads(GEO_FEED_PATH.read_text(encoding="utf-8")); ts=datetime.fromisoformat(j["generated_at"].replace("Z","+00:00"))
        age=(utc_now()-ts.astimezone(timezone.utc)).total_seconds()/60
        if age>GEO_FEED_MAX_AGE_MINUTES: return {**base,"status":"stale"}
        adj=clamp(float(j.get("score_adjustment",0)),-GEO_MAX_SCORE_ADJUSTMENT,GEO_MAX_SCORE_ADJUSTMENT)
        return {"score_adjustment":adj,"status":"live","active_event_count":int(j.get("active_event_count",len(j.get("active_events",[]))))}
    except Exception: return {**base,"status":"error"}

def relative_context(symbol,snaps):
    """Cross-market context without circular self-confirmation."""
    def mom(sym,key="momentum_15m"): return snaps.get(sym,{}).get(key,0.0)
    adj=0.0
    if symbol in {"NVDA","AAPL","AMZN","TSLA"}: adj += clamp(mom("QQQ")/0.015*5,-5,5)
    elif symbol=="WMT": adj += clamp(mom("SPY")/0.012*3,-3,3)
    elif symbol=="XOM": adj += clamp(mom("USO")/0.02*8,-8,8)
    elif symbol=="GLD":
        # SPY weakness can support safe-haven demand, but GLD's own technicals remain primary.
        adj += clamp(-mom("SPY")/0.015*3,-3,3)
    elif symbol=="SPY": adj += clamp(mom("QQQ")/0.015*2,-2,2)
    elif symbol=="QQQ": adj += clamp(mom("SPY")/0.015*2,-2,2)
    return adj

def final_score(symbol,snap,snaps,vix,geo):
    tech=technical_score(snap); pa=premarket_context_adjustment(symbol); ctx=relative_context(symbol,snaps)+pa; va=vix_adjustment(symbol,vix)
    ga=geo["score_adjustment"] if symbol=="XOM" else (clamp(geo["score_adjustment"]*0.25,-2.5,2.5) if symbol=="GLD" else 0.0)
    total=clamp(tech+ctx+va+ga,0,100)
    return total,tech,ctx,va,ga

# ---------------- Portfolio / risk ----------------
def get_position(symbol):
    try:
        p=trading.get_open_position(symbol)
        return {"symbol":symbol,"qty":float(p.qty),"avg_entry_price":float(p.avg_entry_price),"market_value":abs(float(p.market_value)),"unrealized_pl":float(p.unrealized_pl),"current_price":float(p.current_price)}
    except APIError: return None

def all_positions():
    out={}
    try:
        for p in trading.get_all_positions():
            if p.symbol in TRADE_SYMBOLS:
                out[p.symbol]={"symbol":p.symbol,"qty":float(p.qty),"avg_entry_price":float(p.avg_entry_price),"market_value":abs(float(p.market_value)),"unrealized_pl":float(p.unrealized_pl),"current_price":float(p.current_price)}
    except Exception: log.exception("Position fetch failed")
    return out

def trades_today():
    day=utc_now().date().isoformat()
    with db_connect() as c: return int(c.execute("SELECT COUNT(*) n FROM orders WHERE substr(ts,1,10)=?",(day,)).fetchone()["n"])

def realized_today():
    day=utc_now().date().isoformat()
    with db_connect() as c: return float(c.execute("SELECT COALESCE(SUM(pnl),0) p FROM realized WHERE substr(ts,1,10)=?",(day,)).fetchone()["p"])

def market_day_utc_bounds():
    now = market_now()
    start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc).isoformat(), end_local.astimezone(timezone.utc).isoformat()


def stock_eod_stats():
    start_utc, end_utc = market_day_utc_bounds()
    with db_connect() as c:
        realized_rows = list(c.execute(
            "SELECT ts,symbol,pnl FROM realized WHERE ts>=? AND ts<? ORDER BY ts",
            (start_utc, end_utc),
        ))
        order_rows = list(c.execute(
            "SELECT ts,symbol,side,notional FROM orders WHERE ts>=? AND ts<? ORDER BY ts",
            (start_utc, end_utc),
        ))
        best_signal = c.execute(
            "SELECT symbol,score FROM decisions WHERE ts>=? AND ts<? ORDER BY score DESC LIMIT 1",
            (start_utc, end_utc),
        ).fetchone()

    realized = sum(float(r["pnl"] or 0) for r in realized_rows)
    wins = sum(1 for r in realized_rows if float(r["pnl"] or 0) > 0)
    losses = sum(1 for r in realized_rows if float(r["pnl"] or 0) < 0)
    best = max(realized_rows, key=lambda r: float(r["pnl"] or 0)) if realized_rows else None
    worst = min(realized_rows, key=lambda r: float(r["pnl"] or 0)) if realized_rows else None
    buys = sum(1 for r in order_rows if str(r["side"]).lower() == "buy")
    sells = sum(1 for r in order_rows if str(r["side"]).lower() == "sell")

    return {
        "realized": realized,
        "completed": len(realized_rows),
        "wins": wins,
        "losses": losses,
        "best": best,
        "worst": worst,
        "orders": len(order_rows),
        "buys": buys,
        "sells": sells,
        "best_signal": best_signal,
    }


def maybe_send_stock_eod_report():
    """Send one Stock Trader report after the configured ET time, once per market date."""
    if not PUSHOVER_STOCK_EOD_ENABLED:
        return False
    if not PUSHOVER_STOCK_EOD_TOKEN or not PUSHOVER_STOCK_EOD_USER_KEY:
        return False

    now = market_now()
    if now.weekday() >= 5:
        return False
    if (now.hour, now.minute) < (PUSHOVER_STOCK_EOD_HOUR, PUSHOVER_STOCK_EOD_MINUTE):
        return False

    report_date = now.date().isoformat()
    state = load_stock_eod_state()
    if state.get("last_sent_date") == report_date:
        return False

    # Pull the latest fills before summarizing the day.
    sync_fills()
    stats = stock_eod_stats()
    positions = all_positions()
    exposure = sum(p["market_value"] for p in positions.values())
    unrealized = sum(p["unrealized_pl"] for p in positions.values())

    account_day_pnl = None
    account_day_pct = None
    try:
        acct = trading.get_account()
        equity = float(acct.equity)
        last_equity = float(acct.last_equity)
        account_day_pnl = equity - last_equity
        account_day_pct = (account_day_pnl / last_equity * 100.0) if last_equity else 0.0
    except Exception:
        log.exception("Could not read Alpaca account equity for EOD report")

    lines = []
    if account_day_pnl is not None:
        lines.append(f"Account day: ${account_day_pnl:+,.2f} ({account_day_pct:+.2f}%)")
    else:
        lines.append("Account day: unavailable")
    lines.append(f"Realized: ${stats['realized']:+,.2f} | Completed: {stats['completed']}")
    lines.append(f"W/L: {stats['wins']}/{stats['losses']} | Orders B/S: {stats['buys']}/{stats['sells']}")

    if stats["completed"]:
        lines.append(
            f"Best: {stats['best']['symbol']} ${float(stats['best']['pnl']):+,.2f} | "
            f"Worst: {stats['worst']['symbol']} ${float(stats['worst']['pnl']):+,.2f}"
        )
    else:
        lines.append("No completed trades today.")

    lines.append(
        f"Open positions: {len(positions)} | Exposure: ${exposure:,.0f} | "
        f"Unrealized: ${unrealized:+,.2f}"
    )
    if stats["best_signal"]:
        lines.append(
            f"Best signal: {stats['best_signal']['symbol']} "
            f"{float(stats['best_signal']['score']):.1f}"
        )

    sent = send_stock_eod_pushover(
        "Stock Trader — EOD Performance",
        "\n".join(lines),
    )
    if sent:
        save_stock_eod_state({
            "last_sent_date": report_date,
            "sent_at": now.isoformat(),
        })
        log.info("Stock EOD Pushover report sent")
    return sent


def sync_fills():
    """Long-only FIFO-ish ledger per symbol from Alpaca closed orders."""
    try:
        req=GetOrdersRequest(status="closed",symbols=TRADE_SYMBOLS,limit=500)
        orders=list(trading.get_orders(filter=req))
    except Exception: return
    fills=[]
    for o in orders:
        fq=float(getattr(o,"filled_qty",0) or 0); fp=float(getattr(o,"filled_avg_price",0) or 0); ft=getattr(o,"filled_at",None)
        if fq>0 and fp>0 and ft and str(getattr(o,"symbol","")) in TRADE_SYMBOLS:
            side=str(o.side).lower().split(".")[-1]; fills.append((ft,str(o.id),o.symbol,side,fq,fp))
    fills.sort(key=lambda x:x[0])
    with db_connect() as c:
        existing={r[0] for r in c.execute("SELECT alpaca_order_id FROM fills")}
        inventory={}
        for r in c.execute("SELECT symbol,side,qty,price FROM fills ORDER BY ts"):
            q,cost=inventory.get(r[0],(0.0,0.0))
            if r[1]=="buy": inventory[r[0]]=(q+r[2],cost+r[2]*r[3])
            elif q>0:
                sold=min(q,r[2]); avg=cost/q; inventory[r[0]]=(q-sold,cost-avg*sold)
        for ft,oid,sym,side,qty,price in fills:
            if oid in existing: continue
            q,cost=inventory.get(sym,(0.0,0.0)); pnl=None
            if side=="buy": inventory[sym]=(q+qty,cost+qty*price)
            elif q>0:
                sold=min(q,qty); avg=cost/q; pnl=(price-avg)*sold; inventory[sym]=(q-sold,cost-avg*sold)
            c.execute("INSERT OR IGNORE INTO fills VALUES(?,?,?,?,?,?)",(oid,ft.astimezone(timezone.utc).isoformat(),sym,side,qty,price))
            if pnl is not None: c.execute("INSERT INTO realized(ts,symbol,pnl) VALUES(?,?,?)",(ft.astimezone(timezone.utc).isoformat(),sym,pnl))

def market_is_open(): return bool(trading.get_clock().is_open)

# confirmation/high-water are process state; rebuilt naturally after restart
buy_counts={s:0 for s in TRADE_SYMBOLS}; sell_counts={s:0 for s in TRADE_SYMBOLS}; highs={}

def decide(symbol,score,position,price):
    if position:
        entry=position["avg_entry_price"]; pnl=pct_change(price,entry); highs[symbol]=max(highs.get(symbol,price),price)
        if pnl <= -STOP_LOSS_PCT: return "SELL",f"hard stop {pnl:.2%}"
        if pnl >= TAKE_PROFIT_PCT: return "SELL",f"take profit {pnl:.2%}"
        if pct_change(highs[symbol],entry)>=TRAILING_STOP_ACTIVATION_PCT and pct_change(price,highs[symbol])<=-TRAILING_STOP_PCT:
            return "SELL",f"trailing stop; high ${highs[symbol]:.2f}"
        sell_counts[symbol]=sell_counts[symbol]+1 if score<=SELL_SCORE_THRESHOLD else 0
        buy_counts[symbol]=0
        if sell_counts[symbol]>=SELL_CONFIRMATIONS: sell_counts[symbol]=0; return "SELL",f"score {score:.1f} <= {SELL_SCORE_THRESHOLD} confirmed"
        return "HOLD",f"position open; score {score:.1f}; pnl {pnl:.2%}"
    highs.pop(symbol,None); sell_counts[symbol]=0
    buy_counts[symbol]=buy_counts[symbol]+1 if score>=BUY_SCORE_THRESHOLD else 0
    if buy_counts[symbol]>=BUY_CONFIRMATIONS: buy_counts[symbol]=0; return "BUY",f"score {score:.1f} >= {BUY_SCORE_THRESHOLD} confirmed"
    return "HOLD",f"no position; score {score:.1f}; buy confirm {buy_counts[symbol]}/{BUY_CONFIRMATIONS}"

def place_buy(symbol,price,reason,positions):
    if len(positions)>=MAX_OPEN_POSITIONS: return False,"max open positions"
    exposure=sum(p["market_value"] for p in positions.values())
    room=max(0,MAX_TOTAL_EXPOSURE-exposure); notional=min(MAX_TRADE_DOLLARS,room)
    if notional<10: return False,"portfolio exposure limit"
    if trades_today()>=MAX_TRADES_PER_DAY: return False,"daily trade limit"
    if realized_today()<=-MAX_DAILY_REALIZED_LOSS: return False,"daily realized loss limit"
    try:
        o=trading.submit_order(order_data=MarketOrderRequest(symbol=symbol,notional=round(notional,2),side=OrderSide.BUY,time_in_force=TimeInForce.DAY))
        row={"id":str(uuid.uuid4()),"ts":utc_now().isoformat(),"symbol":symbol,"side":"buy","qty":0,"price":price,"notional":notional,"reason":reason,"alpaca_order_id":str(o.id)}
        with db_connect() as c: c.execute("INSERT INTO orders VALUES(:id,:ts,:symbol,:side,:qty,:price,:notional,:reason,:alpaca_order_id)",row)
        append_csv(daily_paths()["trades"],row); send_pushover(f"PAPER BUY {symbol}",f"${notional:,.0f} near ${price:.2f}\n{reason}")
        return True,"submitted"
    except Exception as e: log.exception("BUY failed %s",symbol); return False,str(e)

def place_sell(symbol,position,price,reason):
    try:
        o=trading.submit_order(order_data=MarketOrderRequest(symbol=symbol,qty=abs(position["qty"]),side=OrderSide.SELL,time_in_force=TimeInForce.DAY))
        row={"id":str(uuid.uuid4()),"ts":utc_now().isoformat(),"symbol":symbol,"side":"sell","qty":abs(position["qty"]),"price":price,"notional":abs(position["qty"])*price,"reason":reason,"alpaca_order_id":str(o.id)}
        with db_connect() as c: c.execute("INSERT INTO orders VALUES(:id,:ts,:symbol,:side,:qty,:price,:notional,:reason,:alpaca_order_id)",row)
        append_csv(daily_paths()["trades"],row); send_pushover(f"PAPER SELL {symbol}",f"{abs(position['qty']):g} shares near ${price:.2f}\n{reason}")
        return True,"submitted"
    except Exception as e: log.exception("SELL failed %s",symbol); return False,str(e)

# ---------------- Main cycle ----------------
def write_state(rows,vix,geo,regime,financial_shadow,positions,market_open):
    state={"generated_at":utc_now().isoformat(),"market_open":market_open,"paper_only":True,"vix":vix,"geo":geo,"market_regime_shadow":regime,"financial_leverage_shadow":financial_shadow,
           "portfolio":{"open_positions":len(positions),"exposure":sum(p["market_value"] for p in positions.values()),"realized_today":realized_today(),"trades_today":trades_today()},
           "signals":rows,"positions":list(positions.values())}
    tmp=STATE_PATH.with_suffix(STATE_PATH.suffix+".tmp"); tmp.write_text(json.dumps(state,indent=2),encoding="utf-8"); tmp.replace(STATE_PATH)


def run_once():
    sync_fills(); open_now=market_is_open(); geo=geo_snapshot(); vix=fetch_vix(); regime=market_regime_shadow(vix); maybe_log_market_regime(regime)
    needed=list(dict.fromkeys(TRADE_SYMBOLS+CONTEXT_SYMBOLS+SHADOW_FINANCIAL_SYMBOLS)); snaps={}
    for sym in needed:
        try: snaps[sym]=snapshot(sym)
        except Exception as e: log.warning("Snapshot failed %s: %s",sym,e)
    fin_shadow=financial_leverage_shadow(snaps,regime,vix)
    maybe_log_financial_leverage_shadow(fin_shadow)
    maybe_log_financial_leverage_signal(fin_shadow)
    capture_financial_leverage_outcomes(fin_shadow)
    positions=all_positions(); rows=[]
    # Rank buys so portfolio capital goes to strongest scores first.
    candidates=[]
    for sym in TRADE_SYMBOLS:
        if sym not in snaps: continue
        score,tech,ctx,va,ga=final_score(sym,snaps[sym],snaps,vix,geo)
        decision,reason=decide(sym,score,positions.get(sym),snaps[sym]["price"])
        audit=funnel_context(sym,score,decision,positions,open_now)
        premarket_adj=premarket_context_adjustment(sym)
        rec={**snaps[sym],"score":score,"technical":tech,"context":ctx,"premarket_adjustment":premarket_adj,"vix_adjustment":va,"geo_adjustment":ga,"decision":decision,"reason":reason,
             "position":bool(positions.get(sym)),"unrealized_pl":positions.get(sym,{}).get("unrealized_pl",0.0)}
        if audit:
            rec["_decision_event_id"]=audit["event_id"]
        rows.append(rec)
        if audit and audit.get("side") == "BUY":
            log_regime_decision_shadow(audit.get("event_id"), rec, regime)

        if decision=="BUY":
            candidates.append(rec)
        elif decision=="SELL":
            if open_now:
                ok,msg=place_sell(sym,positions[sym],snaps[sym]["price"],reason)
                attempted=_order_was_attempted(msg)
                gate=_audit_gate_reason(msg,attempted=attempted,accepted=ok)
                order_id=latest_order_id(sym,"sell") if ok else ""
                log_order_attempt(
                    decision_event_id=audit["event_id"],symbol=sym,side="SELL",
                    attempted=attempted,accepted=ok,gate_reason=gate,alpaca_order_id=order_id,
                )
                audit["final_disposition"]="ORDER_SUBMITTED" if ok else "ORDER_REJECTED"
                audit["gate_reason"]=gate
            else:
                gate="MARKET_CLOSED"
                log_order_attempt(
                    decision_event_id=audit["event_id"],symbol=sym,side="SELL",
                    attempted=False,accepted=False,gate_reason=gate,
                )
                audit["final_disposition"]="BLOCKED"
                audit["gate_reason"]=gate
            log_decision_funnel(**audit,decision_reason=reason)
        elif audit:
            audit["final_disposition"]="AWAITING_CONFIRMATION"
            audit["gate_reason"]="AWAITING_CONFIRMATION"
            log_decision_funnel(**audit,decision_reason=reason)

        drow={"id":str(uuid.uuid4()),"ts":utc_now().isoformat(),"symbol":sym,"price":snaps[sym]["price"],"score":score,"decision":decision,"technical":tech,"context":ctx,"premarket_adjustment":premarket_adj,"vix_adjustment":va,"geo_adjustment":ga,
              "momentum_5m":snaps[sym]["momentum_5m"],"momentum_15m":snaps[sym]["momentum_15m"],"rsi14":snaps[sym]["rsi14"],"volume_ratio":snaps[sym]["volume_ratio"],"vix_level":vix.get("level"),"vix_5m":vix.get("change_5m",0),"vix_15m":vix.get("change_15m",0),"reason":reason}
        with db_connect() as c: c.execute("INSERT INTO decisions VALUES(:id,:ts,:symbol,:price,:score,:decision,:technical,:context,:vix_adjustment,:geo_adjustment,:momentum_5m,:momentum_15m,:rsi14,:volume_ratio,:vix_level,:vix_5m,:vix_15m,:reason)",drow)
        append_csv(daily_paths()["decisions"],drow)

    if open_now:
        for rec in sorted(candidates,key=lambda x:x["score"],reverse=True):
            event_id=rec["_decision_event_id"]
            audit=funnel_context(rec["symbol"],rec["score"],"BUY",positions,open_now)
            audit["event_id"]=event_id
            ok,msg=place_buy(rec["symbol"],rec["price"],rec["reason"],positions)
            attempted=_order_was_attempted(msg)
            gate=_audit_gate_reason(msg,attempted=attempted,accepted=ok)
            order_id=latest_order_id(rec["symbol"],"buy") if ok else ""
            log_order_attempt(
                decision_event_id=event_id,symbol=rec["symbol"],side="BUY",
                attempted=attempted,accepted=ok,gate_reason=gate,alpaca_order_id=order_id,
            )
            audit["final_disposition"]="ORDER_SUBMITTED" if ok else "ORDER_REJECTED"
            audit["gate_reason"]=gate
            log_decision_funnel(**audit,decision_reason=rec["reason"])
            if ok: positions=all_positions()
    else:
        for rec in candidates:
            event_id=rec["_decision_event_id"]
            audit=funnel_context(rec["symbol"],rec["score"],"BUY",positions,open_now)
            audit["event_id"]=event_id
            log_order_attempt(
                decision_event_id=event_id,symbol=rec["symbol"],side="BUY",
                attempted=False,accepted=False,gate_reason="MARKET_CLOSED",
            )
            audit["final_disposition"]="BLOCKED"
            audit["gate_reason"]="MARKET_CLOSED"
            log_decision_funnel(**audit,decision_reason=rec["reason"])

    for rec in rows:
        rec.pop("_decision_event_id",None)
    rows.sort(key=lambda x:x["score"],reverse=True)
    write_state(rows,vix,geo,regime,fin_shadow,positions,open_now)
    lead=" | ".join(f"{r['symbol']} {r['score']:.1f} {r['decision']}" for r in rows[:5])
    log.info("REGIME=%s %.0f | FIN_SHADOW=%s %.0f | VIX=%s %.2f%%/15m | %s", regime.get("state"), float(regime.get("score") or 0), fin_shadow.get("candidate"), float(fin_shadow.get("score") or 0), f"{vix['level']:.2f}" if vix.get('level') is not None else vix['source'], vix.get('change_15m',0)*100, lead)
    if not open_now: log.info("TEST MODE: market closed — no orders submitted")

def main():
    init_db(); acct=trading.get_account()
    log.info("Momentum Trader v1.8 PAPER ONLY + MARKET-AWARE + PREMARKET INTELLIGENCE | account=%s | symbols=%s",acct.status,",".join(TRADE_SYMBOLS))
    log.info("Market data feed: %s", ALPACA_DATA_FEED_NAME.upper())
    log.info("Dashboard state: %s", STATE_PATH)
    log.info("Premarket: %s | start %dm before open | refresh offsets=%s | social=%s",
             "ENABLED" if PREMARKET_ENABLED else "DISABLED",
             PREMARKET_START_MINUTES,
             ",".join(str(x) for x in PREMARKET_REFRESH_OFFSETS),
             PREMARKET_SOCIAL_SOURCE)
    log.info("Stock EOD Pushover: %s @ %02d:%02d ET", "ENABLED" if (PUSHOVER_STOCK_EOD_ENABLED and PUSHOVER_STOCK_EOD_TOKEN and PUSHOVER_STOCK_EOD_USER_KEY) else "NOT CONFIGURED", PUSHOVER_STOCK_EOD_HOUR, PUSHOVER_STOCK_EOD_MINUTE)
    log.info("Limits: $%.0f/trade | $%.0f exposure | %d positions | %d trades/day | $%.0f daily loss",MAX_TRADE_DOLLARS,MAX_TOTAL_EXPOSURE,MAX_OPEN_POSITIONS,MAX_TRADES_PER_DAY,MAX_DAILY_REALIZED_LOSS)

    while True:
        try:
            clock = trading.get_clock()
            now = utc_now()

            if bool(clock.is_open):
                session_date = market_now().date().isoformat()
                if _PREMARKET_CONTEXT.get("session_date") != session_date:
                    load_latest_premarket_context(session_date)

                warmup = market_warmup_remaining_minutes()
                if warmup > 0:
                    target = now + timedelta(minutes=warmup)
                    sleep_until(target, f"MARKET OPEN WARMUP ({warmup:.0f}m remaining)")
                    continue

                started=time.monotonic()
                run_once()
                maybe_send_stock_eod_report()
                time.sleep(max(1,CHECK_INTERVAL_SECONDS-(time.monotonic()-started)))
                continue

            # Market closed: never request the full one-minute snapshot universe.
            now_et = market_now()
            eod_target = eod_due_target(now_et)
            if eod_target is not None:
                if eod_target <= now_et:
                    maybe_send_stock_eod_report()
                else:
                    sleep_until(eod_target.astimezone(timezone.utc), "MARKET CLOSED — waiting for EOD report")
                    continue

            next_open = _aware_utc(clock.next_open)
            premarket_start = next_open - timedelta(minutes=PREMARKET_START_MINUTES)

            if PREMARKET_ENABLED and now >= premarket_start and now < next_open:
                maybe_run_premarket(clock)
                target = next_premarket_due(clock)
                sleep_until(target, "PREMARKET INTELLIGENCE")
                continue

            # Overnight/weekend/holiday idle: sleep to the next useful event.
            sleep_until(premarket_start if PREMARKET_ENABLED else next_open, "MARKET CLOSED — idle")

        except KeyboardInterrupt:
            log.info("Stopped by user")
            break
        except Exception:
            log.exception("Scheduler cycle failed")
            time.sleep(30)

if __name__=="__main__": main()
