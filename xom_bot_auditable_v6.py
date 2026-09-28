"""
XOM paper-trading bot V6 - regime-aware, confirmation-based paper strategy.

What it does:
- Runs continuously.
- Only evaluates during the regular U.S. market session.
- Pulls recent XOM 1-minute bars from Alpaca.
- Calculates simple momentum, SMA20, RSI14, and relative volume.
- Polls Alpaca's news endpoint for new XOM articles.
- Sends each unseen article to OpenAI for structured sentiment/materiality analysis.
- Combines technical + news signals.
- Applies hard risk limits.
- Places PAPER trades only.
- Keeps SQLite as the master history and creates daily audit/CSV files.

IMPORTANT:
This is a starter/testing strategy, not a validated profitable strategy.
It intentionally refuses to run as a live-money bot.
"""

import csv
import json
import logging
import os
import sqlite3
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from openai import OpenAI

from alpaca.common.exceptions import APIError
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest


# ----------------------------
# Configuration
# ----------------------------

load_dotenv()

SYMBOL = "XOM"
OIL_PROXY = "USO"  # United States Oil Fund; used as a crude-oil proxy in V1
PAPER_ONLY = True

ALPACA_API_KEY = os.environ["ALPACA_API_KEY"]
ALPACA_SECRET_KEY = os.environ["ALPACA_SECRET_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# Use a model available to your API account.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

# Pushover: accepts several common .env variable names.
PUSHOVER_API_TOKEN = (
    os.getenv("PUSHOVER_API_TOKEN")
    or os.getenv("PUSHOVER_APP_TOKEN")
    or os.getenv("PUSHOVER_TOKEN")
)
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY") or os.getenv("PUSHOVER_USER")
PUSHOVER_ENABLED = bool(PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY)
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))

# Conservative demo limits. Change only after paper testing.
MAX_POSITION_DOLLARS = float(os.getenv("MAX_POSITION_DOLLARS", "10000"))
MAX_TRADE_DOLLARS = float(os.getenv("MAX_TRADE_DOLLARS", "2500"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "4"))
MAX_DAILY_REALIZED_LOSS = float(os.getenv("MAX_DAILY_REALIZED_LOSS", "300"))

STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.02"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.03"))

BUY_SCORE_THRESHOLD = float(os.getenv("BUY_SCORE_THRESHOLD", "70"))
SELL_SCORE_THRESHOLD = float(os.getenv("SELL_SCORE_THRESHOLD", "30"))

DB_PATH = Path(os.getenv("DB_PATH", "xom_bot.sqlite3"))
STRATEGY_REVIEW_INTERVAL_MINUTES = int(os.getenv("STRATEGY_REVIEW_INTERVAL_MINUTES", "60"))
STRATEGY_REVIEW_LOOKBACK_HOURS = int(os.getenv("STRATEGY_REVIEW_LOOKBACK_HOURS", "24"))
STRATEGY_REVIEW_MIN_DECISIONS = int(os.getenv("STRATEGY_REVIEW_MIN_DECISIONS", "30"))

# V6 signal-stability / regime settings.
NEWS_MIN_MATERIALITY = float(os.getenv("NEWS_MIN_MATERIALITY", "0.10"))
NEWS_SHOCK_MATERIALITY = float(os.getenv("NEWS_SHOCK_MATERIALITY", "0.55"))
NEWS_SHOCK_LOOKBACK_HOURS = int(os.getenv("NEWS_SHOCK_LOOKBACK_HOURS", "18"))
BUY_CONFIRMATIONS = int(os.getenv("BUY_CONFIRMATIONS", "2"))
SELL_CONFIRMATIONS = int(os.getenv("SELL_CONFIRMATIONS", "2"))
TRAILING_STOP_ACTIVATION_PCT = float(os.getenv("TRAILING_STOP_ACTIVATION_PCT", "0.01"))
TRAILING_STOP_PCT = float(os.getenv("TRAILING_STOP_PCT", "0.0125"))

# In-memory confirmation/high-water state. Safe to reset on restart; hard risk limits remain independent.
_buy_confirmation_count = 0
_sell_confirmation_count = 0
_position_high_water = None

ALPACA_NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
LOG_ROOT = Path(os.getenv("LOG_ROOT", "logs"))
MARKET_TZ = ZoneInfo("America/New_York")

# These symbols/keywords broaden the feed beyond articles tagged directly to XOM.
ENERGY_WATCH_SYMBOLS = {
    "XOM", "USO", "XLE", "CVX", "OXY", "COP", "MPC", "VLO", "PSX"
}

ENERGY_GEO_KEYWORDS = {
    "iran", "iranian", "tehran", "strait of hormuz", "hormuz",
    "persian gulf", "gulf", "red sea", "houthi", "houthis",
    "israel", "israeli", "opec", "opec+", "saudi", "saudi arabia",
    "crude", "crude oil", "oil price", "oil prices", "petroleum",
    "tanker", "tankers", "shipping", "sanction", "sanctions",
    "refinery", "refining", "pipeline", "pipelines",
    "natural gas", "lng", "energy supply", "production cut",
    "production cuts", "oil supply", "energy infrastructure"
}



# ----------------------------
# Daily audit / CSV files
# ----------------------------

def market_now():
    """Current time in the U.S. Eastern market timezone."""
    return datetime.now(MARKET_TZ)


def daily_paths():
    """
    Return today's audit paths using the New York trading date.

    Example:
      logs/2026-09-14/decisions.csv
      logs/2026-09-14/trades.csv
      logs/2026-09-14/news.log
      logs/2026-09-14/llm.log

    Recomputed on every write so a bot left running overnight automatically
    rolls into a new folder on the next market date.
    """
    day = market_now().date().isoformat()
    folder = LOG_ROOT / day
    folder.mkdir(parents=True, exist_ok=True)

    return {
        "folder": folder,
        "decisions": folder / "decisions.csv",
        "trades": folder / "trades.csv",
        "news": folder / "news.log",
        "llm": folder / "llm.log",
    }


def append_csv(path, fieldnames, row):
    """Append one row and create the CSV header automatically if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


DECISION_CSV_FIELDS = [
    "timestamp_utc",
    "timestamp_et",
    "symbol",
    "price",
    "momentum_5m",
    "momentum_15m",
    "rsi14",
    "sma20",
    "volume_ratio",
    "oil_symbol",
    "oil_price",
    "oil_momentum_5m",
    "oil_momentum_15m",
    "oil_above_sma20",
    "news_sentiment",
    "news_materiality",
    "news_confidence",
    "score",
    "decision",
    "reason",
    "position_qty",
    "position_avg_entry",
]

TRADE_CSV_FIELDS = [
    "timestamp_utc",
    "timestamp_et",
    "symbol",
    "side",
    "qty",
    "estimated_price",
    "estimated_notional",
    "reason",
    "client_order_id",
    "alpaca_order_id",
    "status",
]

# ----------------------------
# Logging
# ----------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("xom_bot")


# ----------------------------
# Clients
# ----------------------------

if not PAPER_ONLY:
    raise RuntimeError("This starter is intentionally paper-only.")

trading = TradingClient(
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    paper=True,
)

market_data = StockHistoricalDataClient(
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
)

llm = OpenAI(api_key=OPENAI_API_KEY)


# ----------------------------
# SQLite
# ----------------------------

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS news (
                article_id TEXT PRIMARY KEY,
                created_at TEXT,
                headline TEXT,
                source TEXT,
                sentiment REAL,
                materiality REAL,
                confidence REAL,
                xom_impact TEXT,
                oil_impact TEXT,
                supply_impact TEXT,
                category TEXT,
                time_horizon TEXT,
                reason TEXT,
                risk_note TEXT
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                price REAL,
                momentum_5m REAL,
                momentum_15m REAL,
                rsi14 REAL,
                sma20 REAL,
                volume_ratio REAL,
                oil_price REAL,
                oil_momentum_5m REAL,
                oil_momentum_15m REAL,
                oil_above_sma20 INTEGER,
                news_sentiment REAL,
                news_materiality REAL,
                news_confidence REAL,
                score REAL,
                decision TEXT,
                reason TEXT
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                client_order_id TEXT UNIQUE,
                alpaca_order_id TEXT,
                side TEXT,
                qty REAL,
                notional_estimate REAL,
                reason TEXT
            );

            CREATE TABLE IF NOT EXISTS fills (
                order_id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                side TEXT NOT NULL,
                qty REAL NOT NULL,
                price REAL NOT NULL,
                realized_pl REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS strategy_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                review_json TEXT NOT NULL
            );
            """
        )


def migrate_db():
    """
    Adds new audit columns to an existing SQLite DB without requiring you
    to delete your prior test history.
    """
    with db_connect() as conn:
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(news)").fetchall()
        }
        additions = {
            "xom_impact": "TEXT",
            "oil_impact": "TEXT",
            "supply_impact": "TEXT",
            "risk_note": "TEXT",
        }
        for column, column_type in additions.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE news ADD COLUMN {column} {column_type}")


# ----------------------------
# Utility / indicators
# ----------------------------

def utc_now():
    return datetime.now(timezone.utc)


def pct_change(new, old):
    if old in (None, 0):
        return 0.0
    return (new / old) - 1.0


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def rsi(values, period=14):
    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(-period, 0):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def get_recent_bars(symbol):
    # Pull enough history for indicators even shortly after market open.
    start = utc_now() - timedelta(days=5)

    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        limit=1000,
    )

    result = market_data.get_stock_bars(req)
    bars = list(result[symbol])

    if len(bars) < 30:
        raise RuntimeError(f"Only received {len(bars)} bars for {symbol}; need at least 30.")

    return bars


def market_snapshot():
    bars = get_recent_bars(SYMBOL)

    closes = [float(b.close) for b in bars]
    volumes = [float(b.volume) for b in bars]

    price = closes[-1]

    momentum_5m = pct_change(price, closes[-6]) if len(closes) >= 6 else 0.0
    momentum_15m = pct_change(price, closes[-16]) if len(closes) >= 16 else 0.0

    sma20_value = sma(closes, 20)
    rsi14_value = rsi(closes, 14)

    avg_vol_20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else 0
    volume_ratio = (volumes[-1] / avg_vol_20) if avg_vol_20 else 1.0

    return {
        "price": price,
        "momentum_5m": momentum_5m,
        "momentum_15m": momentum_15m,
        "sma20": sma20_value,
        "rsi14": rsi14_value,
        "volume_ratio": volume_ratio,
    }


def oil_snapshot():
    """
    V1 uses USO as a readily available Alpaca-tradable crude-oil proxy.
    It is context only; the bot never trades USO.
    """
    bars = get_recent_bars(OIL_PROXY)
    closes = [float(b.close) for b in bars]

    price = closes[-1]
    momentum_5m = pct_change(price, closes[-6]) if len(closes) >= 6 else 0.0
    momentum_15m = pct_change(price, closes[-16]) if len(closes) >= 16 else 0.0
    sma20_value = sma(closes, 20)

    return {
        "symbol": OIL_PROXY,
        "price": price,
        "momentum_5m": momentum_5m,
        "momentum_15m": momentum_15m,
        "sma20": sma20_value,
        "above_sma20": bool(sma20_value and price > sma20_value),
    }


# ----------------------------
# Alpaca account / position
# ----------------------------

def market_is_open():
    clock = trading.get_clock()
    return bool(clock.is_open)


def get_position():
    try:
        position = trading.get_open_position(SYMBOL)
        return {
            "qty": float(position.qty),
            "avg_entry_price": float(position.avg_entry_price),
            "market_value": abs(float(position.market_value)),
            "unrealized_pl": float(position.unrealized_pl),
        }
    except APIError:
        return None


def trades_today():
    today_utc = utc_now().date().isoformat()
    with db_connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM orders WHERE substr(ts, 1, 10) = ?",
            (today_utc,),
        ).fetchone()
    return int(row["n"])


def sync_fills_and_realized_pl():
    """Sync filled XOM orders from Alpaca and maintain a simple long-only realized P/L ledger."""
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, symbols=[SYMBOL], limit=500)
        orders = list(trading.get_orders(filter=req))
    except Exception:
        log.exception("Could not sync fills from Alpaca")
        return

    filled = []
    for o in orders:
        fq = float(getattr(o, "filled_qty", 0) or 0)
        fp = float(getattr(o, "filled_avg_price", 0) or 0)
        ft = getattr(o, "filled_at", None)
        if fq > 0 and fp > 0 and ft:
            filled.append((ft, str(o.id), str(o.side).lower(), fq, fp))
    filled.sort(key=lambda x: x[0])

    qty_held = 0.0
    avg_cost = 0.0
    with db_connect() as conn:
        conn.execute("DELETE FROM fills")
        for ft, oid, side, qty, price in filled:
            realized = 0.0
            if "buy" in side:
                new_qty = qty_held + qty
                avg_cost = ((qty_held * avg_cost) + (qty * price)) / new_qty if new_qty else 0.0
                qty_held = new_qty
            else:
                sell_qty = min(qty, qty_held)
                realized = (price - avg_cost) * sell_qty
                qty_held = max(0.0, qty_held - sell_qty)
                if qty_held == 0:
                    avg_cost = 0.0
            conn.execute(
                "INSERT OR REPLACE INTO fills(order_id, ts, side, qty, price, realized_pl) VALUES (?, ?, ?, ?, ?, ?)",
                (oid, ft.isoformat() if hasattr(ft, "isoformat") else str(ft), side, qty, price, realized),
            )

def realized_loss_today():
    sync_fills_and_realized_pl()
    today_et = market_now().date()
    total = 0.0
    with db_connect() as conn:
        for row in conn.execute("SELECT ts, realized_pl FROM fills").fetchall():
            try:
                dt = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00"))
                if dt.astimezone(MARKET_TZ).date() == today_et:
                    total += float(row["realized_pl"] or 0)
            except Exception:
                continue
    return min(0.0, total)


# ----------------------------
# News
# ----------------------------

def seen_article(article_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM news WHERE article_id = ?",
            (str(article_id),),
        ).fetchone()
    return row is not None


def _alpaca_news_request(params):
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    }

    response = requests.get(
        ALPACA_NEWS_URL,
        params=params,
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("news", [])


def fetch_recent_news():
    """
    Pull two Alpaca/Benzinga feeds:
    1) energy-symbol news
    2) the latest general market news

    The general feed is locally filtered for Iran/Hormuz/OPEC/oil-related terms.
    This helps catch market-moving energy stories that are not tagged XOM.
    """
    start_time = (utc_now() - timedelta(hours=24)).isoformat()

    symbol_params = {
        "symbols": ",".join(sorted(ENERGY_WATCH_SYMBOLS)),
        "limit": 50,
        "sort": "desc",
        "include_content": "true",
        "start": start_time,
    }

    general_params = {
        "limit": 50,
        "sort": "desc",
        "include_content": "true",
        "start": start_time,
    }

    symbol_articles = _alpaca_news_request(symbol_params)
    general_articles = _alpaca_news_request(general_params)

    merged = {}

    for article in symbol_articles + general_articles:
        article_id = article.get("id")
        if article_id is None:
            continue
        merged[str(article_id)] = article

    relevant = []
    for article in merged.values():
        if article_is_relevant(article):
            relevant.append(article)

    return relevant


def article_is_relevant(article):
    symbols = {str(s).upper() for s in (article.get("symbols") or [])}

    # Any watched energy symbol is relevant.
    if symbols & ENERGY_WATCH_SYMBOLS:
        return True

    text_blob = " ".join(
        [
            str(article.get("headline") or ""),
            str(article.get("summary") or ""),
            str(article.get("content") or ""),
        ]
    ).lower()

    return any(keyword in text_blob for keyword in ENERGY_GEO_KEYWORDS)


def article_channel(article):
    symbols = {str(s).upper() for s in (article.get("symbols") or [])}
    text_blob = " ".join(
        [
            str(article.get("headline") or ""),
            str(article.get("summary") or ""),
            str(article.get("content") or ""),
        ]
    ).lower()

    if "XOM" in symbols:
        return "XOM"

    geo_terms = (
        "iran", "iranian", "tehran", "hormuz", "red sea",
        "houthi", "houthis", "israel", "sanction", "tanker"
    )
    if any(term in text_blob for term in geo_terms):
        return "IRAN/GEO"

    return "ENERGY/OIL"


NEWS_SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {
            "type": "number",
            "minimum": -1,
            "maximum": 1,
        },
        "materiality": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "xom_impact": {
            "type": "string",
            "enum": ["positive", "negative", "neutral", "mixed"],
        },
        "oil_impact": {
            "type": "string",
            "enum": ["positive", "negative", "neutral", "mixed"],
        },
        "supply_impact": {
            "type": "string",
            "enum": ["tighter", "looser", "unchanged", "uncertain"],
        },
        "category": {
            "type": "string",
            "enum": [
                "earnings",
                "guidance",
                "oil_prices",
                "natural_gas",
                "opec",
                "geopolitical",
                "sanctions",
                "refining",
                "acquisition",
                "legal",
                "regulatory",
                "analyst",
                "management",
                "product",
                "macro",
                "rumor",
                "other",
            ],
        },
        "time_horizon": {
            "type": "string",
            "enum": ["intraday", "days", "weeks", "long_term"],
        },
        "reason": {
            "type": "string",
        },
        "risk_note": {
            "type": "string",
        },
    },
    "required": [
        "sentiment",
        "materiality",
        "confidence",
        "xom_impact",
        "oil_impact",
        "supply_impact",
        "category",
        "time_horizon",
        "reason",
        "risk_note",
    ],
    "additionalProperties": False,
}



def clean_text(text, max_chars=12000):
    text = (text or "").strip()
    return text[:max_chars]


def analyze_article(article):
    headline = clean_text(article.get("headline"), 1000)
    summary = clean_text(article.get("summary"), 3000)
    content = clean_text(article.get("content"), 12000)

    prompt = f"""
You classify market news for a rules-based XOM paper-trading system.

Ticker: XOM (Exxon Mobil)

Evaluate ONLY the supplied article.
Do not make a buy/sell recommendation and do not invent facts beyond the article.

Return a structured assessment of how the article could affect XOM.

Score:
- sentiment: expected directional effect on XOM, from -1.0 very negative to +1.0 very positive
- materiality: likely importance to XOM's market value, from 0.0 to 1.0
- confidence: confidence that your classification follows from the article, from 0.0 to 1.0

Also classify:
- xom_impact: positive, negative, neutral, or mixed
- oil_impact: whether the development is positive, negative, neutral, or mixed for crude-oil prices
- supply_impact: tighter, looser, unchanged, or uncertain global oil/energy supply conditions
- category
- time_horizon
- reason: concise explanation of the causal mechanism
- risk_note: concise counterargument, offsetting factor, or uncertainty

For geopolitical and energy stories, explicitly reason about whether the event could alter:
- crude supply availability
- shipping through the Strait of Hormuz, Red Sea, or Persian Gulf
- sanctions or exports
- OPEC/OPEC+ production
- tanker/shipping risk
- refinery or pipeline availability
- natural gas/LNG flows
- upstream margins
- downstream/refining margins

Consider Exxon-specific events plus crude oil, natural gas, OPEC/OPEC+,
geopolitical disruptions, Iran, Israel, the Strait of Hormuz, sanctions,
refining margins/outages, acquisitions, earnings, guidance, regulation,
litigation, and major macro energy developments.

Treat rumors and ambiguous reports cautiously. If the article is not clearly
material to XOM, keep materiality low even if the headline is dramatic.

Headline:
{headline}

Summary:
{summary}

Article content:
{content}
"""

    # Show and persist the exact prompt for auditability.
    prompt_block = (
        "\n" + "=" * 90 + "\n"
        + "PROMPT SENT TO OPENAI\n"
        + "=" * 90 + "\n"
        + prompt.strip() + "\n"
        + "=" * 90
    )
    print(prompt_block, flush=True)

    with daily_paths()["llm"].open("a", encoding="utf-8") as f:
        f.write(
            f"\nTIMESTAMP_UTC: {utc_now().isoformat()}\n"
            f"ARTICLE_ID: {article.get('id')}\n"
            f"ARTICLE_URL: {article.get('url') or ''}\n"
            + prompt_block + "\n"
        )

    response = llm.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "xom_news_analysis",
                "schema": NEWS_SCHEMA,
                "strict": True,
            }
        },
    )

    raw_response = response.output_text

    response_block = (
        "\n" + "=" * 90 + "\n"
        + "RAW LLM RESPONSE\n"
        + "=" * 90 + "\n"
        + raw_response + "\n"
        + "=" * 90
    )
    print(response_block, flush=True)

    with daily_paths()["llm"].open("a", encoding="utf-8") as f:
        f.write(response_block + "\n")

    return json.loads(raw_response)


def store_news(article, analysis):
    article_id = str(article.get("id"))
    source = article.get("source") or article.get("author") or ""

    with db_connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO news (
                article_id, created_at, headline, source,
                sentiment, materiality, confidence,
                xom_impact, oil_impact, supply_impact,
                category, time_horizon, reason, risk_note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article_id,
                article.get("created_at"),
                article.get("headline"),
                source,
                analysis["sentiment"],
                analysis["materiality"],
                analysis["confidence"],
                analysis["xom_impact"],
                analysis["oil_impact"],
                analysis["supply_impact"],
                analysis["category"],
                analysis["time_horizon"],
                analysis["reason"],
                analysis["risk_note"],
            ),
        )


def display_and_audit_article(article, analysis):
    source = article.get("source") or article.get("author") or "unknown"
    headline = article.get("headline") or ""
    url = article.get("url") or ""
    symbols = ", ".join(article.get("symbols") or []) or "(none)"
    channel = article_channel(article)

    block = (
        "\n"
        + "=" * 78 + "\n"
        + f"NEWS ANALYZED [{channel}]\n"
        + f"SOURCE:      {source}\n"
        + f"HEADLINE:    {headline}\n"
        + f"SYMBOLS:     {symbols}\n"
        + f"URL:         {url}\n"
        + f"CREATED:     {article.get('created_at') or ''}\n"
        + "-" * 78 + "\n"
        + f"LLM SENTIMENT:   {analysis['sentiment']:+.2f}\n"
        + f"MATERIALITY:      {analysis['materiality']:.2f}\n"
        + f"CONFIDENCE:       {analysis['confidence']:.2f}\n"
        + f"XOM IMPACT:       {analysis['xom_impact']}\n"
        + f"OIL IMPACT:       {analysis['oil_impact']}\n"
        + f"SUPPLY IMPACT:    {analysis['supply_impact']}\n"
        + f"CATEGORY:         {analysis['category']}\n"
        + f"TIME HORIZON:     {analysis['time_horizon']}\n"
        + f"REASON:           {analysis['reason']}\n"
        + f"RISK / OFFSET:    {analysis['risk_note']}\n"
        + "=" * 78
    )

    print(block, flush=True)

    # Persistent audit trail you can open later with Notepad.
    with daily_paths()["news"].open("a", encoding="utf-8") as f:
        f.write(block + "\n")


def process_new_news():
    articles = fetch_recent_news()

    for article in reversed(articles):
        article_id = article.get("id")
        if article_id is None or seen_article(article_id):
            continue

        try:
            analysis = analyze_article(article)
            store_news(article, analysis)
            display_and_audit_article(article, analysis)
            log.info(
                "NEWS | %s | sentiment=%.2f materiality=%.2f confidence=%.2f",
                article.get("headline", "")[:100],
                analysis["sentiment"],
                analysis["materiality"],
                analysis["confidence"],
            )
        except Exception:
            log.exception("Failed processing article %s", article_id)


def aggregate_news_score(hours=6):
    """
    V6: ignore immaterial noise and preserve genuinely material energy shocks longer.
    Returns a weighted directional signal plus a persistent shock component.
    """
    normal_cutoff = (utc_now() - timedelta(hours=hours)).isoformat()
    shock_cutoff = (utc_now() - timedelta(hours=NEWS_SHOCK_LOOKBACK_HOURS)).isoformat()

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT sentiment, materiality, confidence, category, supply_impact
            FROM news
            WHERE created_at >= ? AND materiality >= ?
            """,
            (normal_cutoff, NEWS_MIN_MATERIALITY),
        ).fetchall()
        shock_rows = conn.execute(
            """
            SELECT sentiment, materiality, confidence, category, supply_impact
            FROM news
            WHERE created_at >= ? AND materiality >= ?
              AND category IN ('geopolitical','sanctions','opec','oil_prices','refining')
            """,
            (shock_cutoff, NEWS_SHOCK_MATERIALITY),
        ).fetchall()

    def weighted_signal(items):
        weighted_sum = 0.0
        total_weight = 0.0
        for row in items:
            weight = float(row["materiality"]) * float(row["confidence"])
            weighted_sum += float(row["sentiment"]) * weight
            total_weight += weight
        return weighted_sum / total_weight if total_weight else 0.0

    base_sentiment = weighted_signal(rows)
    shock_sentiment = weighted_signal(shock_rows)

    # Keep a material shock from being averaged away by a flood of low-value stories.
    if shock_rows and abs(shock_sentiment) > abs(base_sentiment):
        sentiment = (0.65 * base_sentiment) + (0.35 * shock_sentiment)
    else:
        sentiment = base_sentiment

    if not rows and not shock_rows:
        return {"sentiment": 0.0, "materiality": 0.0, "confidence": 0.0, "shock_sentiment": 0.0, "shock_count": 0}

    source_rows = rows or shock_rows
    return {
        "sentiment": sentiment,
        "materiality": max((float(r["materiality"]) for r in source_rows), default=0.0),
        "confidence": sum(float(r["confidence"]) for r in source_rows) / len(source_rows),
        "shock_sentiment": shock_sentiment,
        "shock_count": len(shock_rows),
    }


# ----------------------------
# Decision engine
# ----------------------------

def _clamp(value, low, high):
    return max(low, min(high, value))

def technical_score(snap):
    """V6 continuous score: avoids large jumps at arbitrary indicator cutoffs."""
    score = 50.0
    sma20 = snap.get("sma20") or snap["price"]
    distance = pct_change(snap["price"], sma20)
    score += _clamp(distance / 0.006 * 10.0, -10.0, 10.0)
    score += _clamp(snap["momentum_5m"] / 0.006 * 8.0, -8.0, 8.0)
    score += _clamp(snap["momentum_15m"] / 0.012 * 12.0, -12.0, 12.0)

    vol_excess = max(0.0, snap["volume_ratio"] - 1.0)
    direction = 1.0 if snap["momentum_5m"] > 0 else (-1.0 if snap["momentum_5m"] < 0 else 0.0)
    score += direction * _clamp(vol_excess * 4.0, 0.0, 6.0)

    rsi14 = snap.get("rsi14") or 50.0
    if rsi14 > 70:
        score -= _clamp((rsi14 - 70) / 15 * 5.0, 0.0, 5.0)
    elif rsi14 < 30:
        score += _clamp((30 - rsi14) / 15 * 5.0, 0.0, 5.0)
    return _clamp(score, 0.0, 100.0)

def oil_regime_score(news, oil):
    """Directional context first; XOM technicals then time the entry."""
    regime = 0.0
    regime += _clamp(oil["momentum_5m"] / 0.008 * 5.0, -5.0, 5.0)
    regime += _clamp(oil["momentum_15m"] / 0.015 * 7.0, -7.0, 7.0)
    regime += 3.0 if oil["above_sma20"] else -3.0
    news_strength = news["sentiment"] * news["materiality"] * news["confidence"]
    regime += _clamp(news_strength * 24.0, -10.0, 10.0)
    if news.get("shock_count", 0):
        regime += _clamp(news.get("shock_sentiment", 0.0) * 8.0, -4.0, 4.0)
    return _clamp(regime, -20.0, 20.0)

def combined_score(snap, news, oil):
    return _clamp(technical_score(snap) + oil_regime_score(news, oil), 0.0, 100.0)


def risk_exit_required(position, current_price):
    global _position_high_water
    if not position:
        _position_high_water = None
        return None

    entry = position["avg_entry_price"]
    return_pct = pct_change(current_price, entry)
    _position_high_water = max(float(_position_high_water or current_price), current_price)

    if return_pct <= -STOP_LOSS_PCT:
        return f"stop loss triggered ({return_pct:.2%})"
    if return_pct >= TAKE_PROFIT_PCT:
        return f"take profit triggered ({return_pct:.2%})"

    high_gain = pct_change(_position_high_water, entry)
    drawdown = pct_change(current_price, _position_high_water)
    if high_gain >= TRAILING_STOP_ACTIVATION_PCT and drawdown <= -TRAILING_STOP_PCT:
        return f"trailing stop triggered (peak {high_gain:.2%}, drawdown {drawdown:.2%})"
    return None

def decide(snap, news, oil, position):
    global _buy_confirmation_count, _sell_confirmation_count
    score = combined_score(snap, news, oil)

    hard_exit = risk_exit_required(position, snap["price"])
    if hard_exit:
        _sell_confirmation_count = 0
        return "SELL", score, hard_exit

    if position:
        _buy_confirmation_count = 0
        if (news["sentiment"] <= -0.65 and news["materiality"] >= 0.65 and news["confidence"] >= 0.75):
            _sell_confirmation_count = 0
            return "SELL", score, "strong negative high-confidence news"
        if score <= SELL_SCORE_THRESHOLD:
            _sell_confirmation_count += 1
            if _sell_confirmation_count >= SELL_CONFIRMATIONS:
                _sell_confirmation_count = 0
                return "SELL", score, f"sell score confirmed {SELL_CONFIRMATIONS} cycles"
            return "HOLD", score, f"sell candidate {_sell_confirmation_count}/{SELL_CONFIRMATIONS}; awaiting confirmation"
        _sell_confirmation_count = 0
        return "HOLD", score, "position open; no exit trigger"

    _sell_confirmation_count = 0
    if trades_today() >= MAX_TRADES_PER_DAY:
        _buy_confirmation_count = 0
        return "HOLD", score, "daily trade limit reached"
    if realized_loss_today() <= -MAX_DAILY_REALIZED_LOSS:
        _buy_confirmation_count = 0
        return "HOLD", score, "daily loss limit reached"

    if score >= BUY_SCORE_THRESHOLD:
        _buy_confirmation_count += 1
        if _buy_confirmation_count >= BUY_CONFIRMATIONS:
            _buy_confirmation_count = 0
            return "BUY", score, f"buy score confirmed {BUY_CONFIRMATIONS} cycles"
        return "HOLD", score, f"buy candidate {_buy_confirmation_count}/{BUY_CONFIRMATIONS}; awaiting confirmation"

    _buy_confirmation_count = 0
    return "HOLD", score, "buy threshold not reached"


# ----------------------------
# Orders
# ----------------------------

def record_order(order, side, qty, notional, reason, client_order_id, estimated_price):
    ts_utc = utc_now()
    ts_et = ts_utc.astimezone(MARKET_TZ)

    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO orders (
                ts, client_order_id, alpaca_order_id,
                side, qty, notional_estimate, reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts_utc.isoformat(),
                client_order_id,
                str(order.id),
                side,
                qty,
                notional,
                reason,
            ),
        )

    append_csv(
        daily_paths()["trades"],
        TRADE_CSV_FIELDS,
        {
            "timestamp_utc": ts_utc.isoformat(),
            "timestamp_et": ts_et.isoformat(),
            "symbol": SYMBOL,
            "side": side,
            "qty": qty,
            "estimated_price": estimated_price,
            "estimated_notional": notional,
            "reason": reason,
            "client_order_id": client_order_id,
            "alpaca_order_id": str(order.id),
            "status": str(getattr(order, "status", "submitted")),
        },
    )


def send_pushover(title, message):
    """Best-effort only: notification failures never stop trading."""
    if not PUSHOVER_ENABLED:
        return False

    payload = urllib.parse.urlencode({
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": title,
        "message": message,
        "priority": "0",
    }).encode("utf-8")

    request = urllib.request.Request(
        PUSHOVER_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "XOM-Paper-Trader/4.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            if result.get("status") == 1:
                log.info("Pushover sent: %s", title)
                return True
            log.error("Pushover rejected notification: %s", result)
    except Exception as exc:
        log.error("Pushover notification failed: %s", exc)
    return False


def trade_push_message(side, qty, price, reason, client_order_id):
    return (
        f"{side} {SYMBOL}\n"
        f"Qty: {qty:.4f}\n"
        f"Est. price: ${price:.2f}\n"
        f"Est. notional: ${qty * price:,.2f}\n"
        f"Reason: {reason}\n"
        f"Time: {market_now().strftime('%Y-%m-%d %I:%M:%S %p ET')}\n"
        f"Order: {client_order_id}"
    )


def place_buy(price, reason):
    position = get_position()
    if position:
        log.warning("BUY blocked: XOM position already exists.")
        return

    dollars = min(MAX_TRADE_DOLLARS, MAX_POSITION_DOLLARS)
    qty = round(dollars / price, 4)

    if qty <= 0:
        return

    client_order_id = f"xom-buy-{uuid.uuid4().hex[:20]}"

    req = MarketOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        client_order_id=client_order_id,
    )

    order = trading.submit_order(order_data=req)
    record_order(order, "BUY", qty, qty * price, reason, client_order_id, price)
    log.warning("=" * 72)
    log.warning("PAPER BUY ORDER SUBMITTED")
    log.warning("Symbol: XOM | Qty: %.4f | Est. notional: $%.2f", qty, qty * price)
    log.warning("Reason: %s", reason)
    log.warning("Client order id: %s", client_order_id)
    log.warning("=" * 72)
    send_pushover(
        "XOM TRADER - PAPER BUY",
        trade_push_message("BUY", qty, price, reason, client_order_id),
    )


def place_sell(position, price, reason):
    if not position:
        return

    qty = float(position["qty"])
    if qty <= 0:
        return

    client_order_id = f"xom-sell-{uuid.uuid4().hex[:20]}"

    req = MarketOrderRequest(
        symbol=SYMBOL,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        client_order_id=client_order_id,
    )

    order = trading.submit_order(order_data=req)
    record_order(order, "SELL", qty, qty * price, reason, client_order_id, price)
    log.warning("=" * 72)
    log.warning("PAPER SELL ORDER SUBMITTED")
    log.warning("Symbol: XOM | Qty: %.4f | Est. notional: $%.2f", qty, qty * price)
    log.warning("Reason: %s", reason)
    log.warning("Client order id: %s", client_order_id)
    log.warning("=" * 72)


def store_decision(snap, news, oil, score, decision, reason, position=None):
    ts_utc = utc_now()
    ts_et = ts_utc.astimezone(MARKET_TZ)

    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO decisions (
                ts, price, momentum_5m, momentum_15m,
                rsi14, sma20, volume_ratio,
                oil_price, oil_momentum_5m, oil_momentum_15m, oil_above_sma20,
                news_sentiment, news_materiality, news_confidence,
                score, decision, reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts_utc.isoformat(),
                snap["price"],
                snap["momentum_5m"],
                snap["momentum_15m"],
                snap["rsi14"],
                snap["sma20"],
                snap["volume_ratio"],
                oil["price"],
                oil["momentum_5m"],
                oil["momentum_15m"],
                1 if oil["above_sma20"] else 0,
                news["sentiment"],
                news["materiality"],
                news["confidence"],
                score,
                decision,
                reason,
            ),
        )

    append_csv(
        daily_paths()["decisions"],
        DECISION_CSV_FIELDS,
        {
            "timestamp_utc": ts_utc.isoformat(),
            "timestamp_et": ts_et.isoformat(),
            "symbol": SYMBOL,
            "price": snap["price"],
            "momentum_5m": snap["momentum_5m"],
            "momentum_15m": snap["momentum_15m"],
            "rsi14": snap["rsi14"],
            "sma20": snap["sma20"],
            "volume_ratio": snap["volume_ratio"],
            "oil_symbol": oil["symbol"],
            "oil_price": oil["price"],
            "oil_momentum_5m": oil["momentum_5m"],
            "oil_momentum_15m": oil["momentum_15m"],
            "oil_above_sma20": int(oil["above_sma20"]),
            "news_sentiment": news["sentiment"],
            "news_materiality": news["materiality"],
            "news_confidence": news["confidence"],
            "score": score,
            "decision": decision,
            "reason": reason,
            "position_qty": position["qty"] if position else 0,
            "position_avg_entry": position["avg_entry_price"] if position else "",
        },
    )


# ----------------------------
# AI strategy review (recommendation-only)
# ----------------------------

STRATEGY_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "assessment": {"type": "string"},
        "missed_moves": {"type": "string"},
        "false_signals": {"type": "string"},
        "news_assessment": {"type": "string"},
        "recommended_change": {"type": "string"},
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "moderate", "high"]}
    },
    "required": ["assessment", "missed_moves", "false_signals", "news_assessment", "recommended_change", "reason", "confidence"],
    "additionalProperties": False
}

def strategy_review_due():
    with db_connect() as conn:
        row = conn.execute("SELECT ts FROM strategy_reviews ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return True
    try:
        last = datetime.fromisoformat(row["ts"])
        return utc_now() - last >= timedelta(minutes=STRATEGY_REVIEW_INTERVAL_MINUTES)
    except Exception:
        return True

def build_strategy_review_payload():
    cutoff = (utc_now() - timedelta(hours=STRATEGY_REVIEW_LOOKBACK_HOURS)).isoformat()
    with db_connect() as conn:
        rows = conn.execute("SELECT * FROM decisions WHERE ts >= ? ORDER BY ts", (cutoff,)).fetchall()
    if len(rows) < STRATEGY_REVIEW_MIN_DECISIONS:
        return None
    data = [dict(r) for r in rows[-500:]]
    # Add forward returns using later observations (~15m and ~60m where available).
    for i, row in enumerate(data):
        p = float(row["price"] or 0)
        for mins, key in ((5, "forward_5m"), (15, "forward_15m"), (30, "forward_30m"), (60, "forward_60m")):
            target = datetime.fromisoformat(row["ts"]) + timedelta(minutes=mins)
            later = next((x for x in data[i+1:] if datetime.fromisoformat(x["ts"]) >= target), None)
            row[key] = pct_change(float(later["price"]), p) if later and p else None
    return data

def run_strategy_review():
    if not strategy_review_due():
        return
    data = build_strategy_review_payload()
    if not data:
        return
    prompt = f"""
You are reviewing a PAPER-TRADING XOM rules engine. Analyze historical decisions and subsequent XOM movement.
Do not make a current buy/sell recommendation. Do not change code or parameters automatically.
Look for missed moves, false positives/negatives, overly restrictive/loose thresholds, and whether the oil/news signal added value.
Current parameters: BUY_SCORE_THRESHOLD={BUY_SCORE_THRESHOLD}, SELL_SCORE_THRESHOLD={SELL_SCORE_THRESHOLD}, STOP_LOSS_PCT={STOP_LOSS_PCT}, TAKE_PROFIT_PCT={TAKE_PROFIT_PCT}, BUY_CONFIRMATIONS={BUY_CONFIRMATIONS}, SELL_CONFIRMATIONS={SELL_CONFIRMATIONS}, TRAILING_STOP_ACTIVATION_PCT={TRAILING_STOP_ACTIVATION_PCT}, TRAILING_STOP_PCT={TRAILING_STOP_PCT}.
Return ONE recommendation at most; say 'no change' when evidence is weak. Treat this as experimental paper-trading analysis, not proof of profitability.

Decision history JSON:
{json.dumps(data, default=str)[:100000]}
"""
    response = llm.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        text={"format": {"type": "json_schema", "name": "xom_strategy_review", "schema": STRATEGY_REVIEW_SCHEMA, "strict": True}},
    )
    review = json.loads(response.output_text)
    with db_connect() as conn:
        conn.execute("INSERT INTO strategy_reviews(ts, review_json) VALUES (?, ?)", (utc_now().isoformat(), json.dumps(review)))
    path = daily_paths()["folder"] / "strategy_reviews.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": utc_now().isoformat(), **review}) + "\n")
    log.info("AI STRATEGY REVIEW | %s | recommendation=%s", review["assessment"], review["recommended_change"])
    if review["recommended_change"].strip().lower() != "no change":
        send_pushover("XOM TRADER - STRATEGY REVIEW", f"{review['recommended_change']}\nConfidence: {review['confidence']}\n{review['reason'][:600]}")

# ----------------------------
# Main loop
# ----------------------------

def run_once():
    if not market_is_open():
        log.info("TEST MODE: Market closed. Evaluating signals but NO orders.")
        test_mode = True
    else:
        test_mode = False

    process_new_news()

    snap = market_snapshot()
    oil = oil_snapshot()
    news = aggregate_news_score(hours=6)
    position = get_position()
    regime = oil_regime_score(news, oil)

    decision, score, reason = decide(snap, news, oil, position)
    store_decision(snap, news, oil, score, decision, reason, position)
    run_strategy_review()

    log.info(
        "%s | $%.2f | 5m=%+.2f%% | 15m=%+.2f%% | RSI=%.1f | "
        "vol=%.2fx | USO15m=%+.2f%% | news=%+.2f | regime=%+.1f | score=%.1f | %s | %s",
        SYMBOL,
        snap["price"],
        snap["momentum_5m"] * 100,
        snap["momentum_15m"] * 100,
        snap["rsi14"],
        snap["volume_ratio"],
        oil["momentum_15m"] * 100,
        news["sentiment"],
        regime,
        score,
        decision,
        reason,
    )

    if test_mode:
        log.info("TEST MODE: Would %s XOM — no order submitted.", decision)
    elif decision == "BUY":
        place_buy(snap["price"], reason)
    elif decision == "SELL":
        place_sell(position, snap["price"], reason)

def main():
    init_db()
    migrate_db()

    account = trading.get_account()
    log.info("Starting XOM PAPER bot.")
    if market_is_open():
        log.warning("TRADING MODE: PAPER — ORDERS ENABLED (market is open)")
    else:
        log.info("TEST MODE: MARKET CLOSED — ORDERS DISABLED")
    log.info("Alpaca account status: %s", account.status)
    log.info("Model: %s", OPENAI_MODEL)
    log.info("Check interval: %ss", CHECK_INTERVAL_SECONDS)
    log.info("V6 confirmations: buy=%s sell=%s | trailing stop activates %.2f%% / trails %.2f%%", BUY_CONFIRMATIONS, SELL_CONFIRMATIONS, TRAILING_STOP_ACTIVATION_PCT*100, TRAILING_STOP_PCT*100)
    if PUSHOVER_ENABLED:
        log.info("Pushover: ENABLED — alerts sent after successful PAPER BUY/SELL submissions")
    else:
        log.warning(
            "Pushover: DISABLED — expected PUSHOVER_API_TOKEN/PUSHOVER_APP_TOKEN "
            "and PUSHOVER_USER_KEY in .env"
        )
    log.info("Database: %s", DB_PATH.resolve())
    paths = daily_paths()
    log.info("Daily log folder: %s", paths["folder"].resolve())
    log.info("Decisions CSV: %s", paths["decisions"].resolve())
    log.info("Trades CSV: %s", paths["trades"].resolve())
    log.info("News audit log: %s", paths["news"].resolve())
    log.info("LLM audit log: %s", paths["llm"].resolve())

    while True:
        started = time.monotonic()

        try:
            run_once()
        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception:
            log.exception("Cycle failed.")

        elapsed = time.monotonic() - started
        sleep_for = max(1, CHECK_INTERVAL_SECONDS - elapsed)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
