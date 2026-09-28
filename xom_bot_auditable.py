"""
XOM paper-trading bot starter.

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

IMPORTANT:
This is a starter/testing strategy, not a validated profitable strategy.
It intentionally refuses to run as a live-money bot.
"""

import json
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

ALPACA_NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
NEWS_AUDIT_PATH = Path(os.getenv("NEWS_AUDIT_PATH", "xom_news_audit.log"))
LLM_AUDIT_PATH = Path(os.getenv("LLM_AUDIT_PATH", "xom_llm_audit.log"))

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


def realized_loss_today():
    """
    Starter safety placeholder.

    We do NOT infer realized P/L from order fills here because accurate realized
    P/L accounting deserves its own fill ledger. Return 0 for V1 and rely on
    Alpaca account controls + stop/position limits.

    Before live trading, replace this with fill-based realized P/L accounting.
    """
    return 0.0


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

    with LLM_AUDIT_PATH.open("a", encoding="utf-8") as f:
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

    with LLM_AUDIT_PATH.open("a", encoding="utf-8") as f:
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
    with NEWS_AUDIT_PATH.open("a", encoding="utf-8") as f:
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
    cutoff = (utc_now() - timedelta(hours=hours)).isoformat()

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT sentiment, materiality, confidence
            FROM news
            WHERE created_at >= ?
            """,
            (cutoff,),
        ).fetchall()

    if not rows:
        return {
            "sentiment": 0.0,
            "materiality": 0.0,
            "confidence": 0.0,
        }

    weighted_sum = 0.0
    total_weight = 0.0
    materiality_sum = 0.0
    confidence_sum = 0.0

    for row in rows:
        weight = float(row["materiality"]) * float(row["confidence"])
        weighted_sum += float(row["sentiment"]) * weight
        total_weight += weight
        materiality_sum += float(row["materiality"])
        confidence_sum += float(row["confidence"])

    return {
        "sentiment": weighted_sum / total_weight if total_weight else 0.0,
        "materiality": materiality_sum / len(rows),
        "confidence": confidence_sum / len(rows),
    }


# ----------------------------
# Decision engine
# ----------------------------

def technical_score(snap):
    score = 50.0

    if snap["price"] > snap["sma20"]:
        score += 8
    else:
        score -= 8

    if snap["momentum_5m"] > 0.003:
        score += 8
    elif snap["momentum_5m"] < -0.003:
        score -= 8

    if snap["momentum_15m"] > 0.0075:
        score += 10
    elif snap["momentum_15m"] < -0.0075:
        score -= 10

    if snap["volume_ratio"] > 1.5:
        if snap["momentum_5m"] > 0:
            score += 6
        elif snap["momentum_5m"] < 0:
            score -= 6

    # Avoid mechanically chasing extremely overbought/oversold readings.
    if snap["rsi14"] >= 75:
        score -= 5
    elif snap["rsi14"] <= 25:
        score += 5

    return max(0, min(100, score))


def combined_score(snap, news, oil):
    tech = technical_score(snap)

    # News shifts the technical score by at most +/-20 points.
    news_strength = (
        news["sentiment"]
        * news["materiality"]
        * news["confidence"]
    )

    # Oil proxy can shift score by up to roughly +/-15 points.
    oil_signal = 0.0

    if oil["momentum_5m"] > 0.004:
        oil_signal += 5
    elif oil["momentum_5m"] < -0.004:
        oil_signal -= 5

    if oil["momentum_15m"] > 0.008:
        oil_signal += 6
    elif oil["momentum_15m"] < -0.008:
        oil_signal -= 6

    if oil["above_sma20"]:
        oil_signal += 4
    else:
        oil_signal -= 4

    score = tech + (20.0 * news_strength) + oil_signal

    return max(0, min(100, score))


def risk_exit_required(position, current_price):
    if not position:
        return None

    entry = position["avg_entry_price"]
    return_pct = pct_change(current_price, entry)

    if return_pct <= -STOP_LOSS_PCT:
        return f"stop loss triggered ({return_pct:.2%})"

    if return_pct >= TAKE_PROFIT_PCT:
        return f"take profit triggered ({return_pct:.2%})"

    return None


def decide(snap, news, oil, position):
    score = combined_score(snap, news, oil)

    hard_exit = risk_exit_required(position, snap["price"])
    if hard_exit:
        return "SELL", score, hard_exit

    if position:
        # Negative high-quality news can trigger an exit.
        if (
            news["sentiment"] <= -0.65
            and news["materiality"] >= 0.65
            and news["confidence"] >= 0.75
        ):
            return "SELL", score, "strong negative high-confidence news"

        if score <= SELL_SCORE_THRESHOLD:
            return "SELL", score, "combined score below sell threshold"

        return "HOLD", score, "position open; no exit trigger"

    # No position
    if trades_today() >= MAX_TRADES_PER_DAY:
        return "HOLD", score, "daily trade limit reached"

    if realized_loss_today() <= -MAX_DAILY_REALIZED_LOSS:
        return "HOLD", score, "daily loss limit reached"

    if score >= BUY_SCORE_THRESHOLD:
        return "BUY", score, "combined score above buy threshold"

    return "HOLD", score, "buy threshold not reached"


# ----------------------------
# Orders
# ----------------------------

def record_order(order, side, qty, notional, reason, client_order_id):
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
                utc_now().isoformat(),
                client_order_id,
                str(order.id),
                side,
                qty,
                notional,
                reason,
            ),
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
    record_order(order, "BUY", qty, qty * price, reason, client_order_id)
    log.warning("PAPER BUY submitted: %.4f XOM (~$%.2f)", qty, qty * price)


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
    record_order(order, "SELL", qty, qty * price, reason, client_order_id)
    log.warning("PAPER SELL submitted: %.4f XOM (~$%.2f)", qty, qty * price)


def store_decision(snap, news, oil, score, decision, reason):
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
                utc_now().isoformat(),
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

    decision, score, reason = decide(snap, news, oil, position)
    store_decision(snap, news, oil, score, decision, reason)

    log.info(
        "%s | $%.2f | 5m=%+.2f%% | 15m=%+.2f%% | RSI=%.1f | "
        "vol=%.2fx | USO15m=%+.2f%% | news=%+.2f | score=%.1f | %s | %s",
        SYMBOL,
        snap["price"],
        snap["momentum_5m"] * 100,
        snap["momentum_15m"] * 100,
        snap["rsi14"],
        snap["volume_ratio"],
        oil["momentum_15m"] * 100,
        news["sentiment"],
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
    log.info("Alpaca account status: %s", account.status)
    log.info("Model: %s", OPENAI_MODEL)
    log.info("Check interval: %ss", CHECK_INTERVAL_SECONDS)
    log.info("Database: %s", DB_PATH.resolve())
    log.info("News audit log: %s", NEWS_AUDIT_PATH.resolve())
    log.info("LLM audit log: %s", LLM_AUDIT_PATH.resolve())

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
