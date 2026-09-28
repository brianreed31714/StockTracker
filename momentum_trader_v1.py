"""
Momentum Trader v1 — multi-asset, PAPER-ONLY trading engine.

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
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest

load_dotenv()

# ---------------- Configuration ----------------
PAPER_ONLY = True
TRADE_SYMBOLS = [s.strip().upper() for s in os.getenv(
    "TRADE_SYMBOLS", "XOM,WMT,AMZN,AAPL,NVDA,TSLA,SPY,QQQ,GLD"
).split(",") if s.strip()]
CONTEXT_SYMBOLS = ["SPY", "QQQ", "GLD", "USO"]
VIX_FALLBACK_SYMBOL = os.getenv("VIX_FALLBACK_SYMBOL", "VIXY")

ALPACA_API_KEY = os.environ["ALPACA_API_KEY"]
ALPACA_SECRET_KEY = os.environ["ALPACA_SECRET_KEY"]
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))

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

DB_PATH = Path(os.getenv("MULTI_DB_PATH", "momentum_trader.sqlite3"))
LOG_ROOT = Path(os.getenv("MULTI_LOG_ROOT", "momentum_logs"))
STATE_PATH = Path(os.getenv("DASHBOARD_STATE_PATH", "dashboard_state.json"))
GEO_FEED_PATH = Path(os.getenv("GEO_FEED_PATH", "geo_feed.json"))
GEO_FEED_MAX_AGE_MINUTES = int(os.getenv("GEO_FEED_MAX_AGE_MINUTES", "15"))
GEO_MAX_SCORE_ADJUSTMENT = float(os.getenv("GEO_MAX_SCORE_ADJUSTMENT", "10"))
MARKET_TZ = ZoneInfo("America/New_York")

PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN") or os.getenv("PUSHOVER_APP_TOKEN") or os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY") or os.getenv("PUSHOVER_USER")
PUSHOVER_ENABLED = bool(PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("momentum_trader")

if not PAPER_ONLY:
    raise RuntimeError("This program is intentionally PAPER ONLY.")

trading = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

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

def daily_paths():
    d = LOG_ROOT / market_now().date().isoformat(); d.mkdir(parents=True, exist_ok=True)
    return {"folder": d, "decisions": d/"decisions.csv", "trades": d/"trades.csv"}

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
        """)

# ---------------- Market data ----------------
def get_recent_bars(symbol, minutes=90):
    end = utc_now(); start = end - timedelta(minutes=minutes + 20)
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, start=start, end=end, limit=minutes+20)
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
    tech=technical_score(snap); ctx=relative_context(symbol,snaps); va=vix_adjustment(symbol,vix)
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
def write_state(rows,vix,geo,positions,market_open):
    state={"generated_at":utc_now().isoformat(),"market_open":market_open,"paper_only":True,"vix":vix,"geo":geo,
           "portfolio":{"open_positions":len(positions),"exposure":sum(p["market_value"] for p in positions.values()),"realized_today":realized_today(),"trades_today":trades_today()},
           "signals":rows,"positions":list(positions.values())}
    tmp=STATE_PATH.with_suffix(STATE_PATH.suffix+".tmp"); tmp.write_text(json.dumps(state,indent=2),encoding="utf-8"); tmp.replace(STATE_PATH)

def run_once():
    sync_fills(); open_now=market_is_open(); geo=geo_snapshot(); vix=fetch_vix()
    needed=list(dict.fromkeys(TRADE_SYMBOLS+CONTEXT_SYMBOLS)); snaps={}
    for sym in needed:
        try: snaps[sym]=snapshot(sym)
        except Exception as e: log.warning("Snapshot failed %s: %s",sym,e)
    positions=all_positions(); rows=[]
    # Rank buys so portfolio capital goes to strongest scores first.
    candidates=[]
    for sym in TRADE_SYMBOLS:
        if sym not in snaps: continue
        score,tech,ctx,va,ga=final_score(sym,snaps[sym],snaps,vix,geo)
        decision,reason=decide(sym,score,positions.get(sym),snaps[sym]["price"])
        rec={**snaps[sym],"score":score,"technical":tech,"context":ctx,"vix_adjustment":va,"geo_adjustment":ga,"decision":decision,"reason":reason,
             "position":bool(positions.get(sym)),"unrealized_pl":positions.get(sym,{}).get("unrealized_pl",0.0)}
        rows.append(rec)
        if decision=="BUY": candidates.append(rec)
        elif decision=="SELL" and open_now: place_sell(sym,positions[sym],snaps[sym]["price"],reason)
        drow={"id":str(uuid.uuid4()),"ts":utc_now().isoformat(),"symbol":sym,"price":snaps[sym]["price"],"score":score,"decision":decision,"technical":tech,"context":ctx,"vix_adjustment":va,"geo_adjustment":ga,
              "momentum_5m":snaps[sym]["momentum_5m"],"momentum_15m":snaps[sym]["momentum_15m"],"rsi14":snaps[sym]["rsi14"],"volume_ratio":snaps[sym]["volume_ratio"],"vix_level":vix.get("level"),"vix_5m":vix.get("change_5m",0),"vix_15m":vix.get("change_15m",0),"reason":reason}
        with db_connect() as c: c.execute("INSERT INTO decisions VALUES(:id,:ts,:symbol,:price,:score,:decision,:technical,:context,:vix_adjustment,:geo_adjustment,:momentum_5m,:momentum_15m,:rsi14,:volume_ratio,:vix_level,:vix_5m,:vix_15m,:reason)",drow)
        append_csv(daily_paths()["decisions"],drow)
    if open_now:
        for rec in sorted(candidates,key=lambda x:x["score"],reverse=True):
            ok,msg=place_buy(rec["symbol"],rec["price"],rec["reason"],positions)
            if ok: positions=all_positions()
    rows.sort(key=lambda x:x["score"],reverse=True)
    write_state(rows,vix,geo,positions,open_now)
    lead=" | ".join(f"{r['symbol']} {r['score']:.1f} {r['decision']}" for r in rows[:5])
    log.info("VIX=%s %.2f%%/15m | %s", f"{vix['level']:.2f}" if vix.get('level') is not None else vix['source'], vix.get('change_15m',0)*100, lead)
    if not open_now: log.info("TEST MODE: market closed — no orders submitted")

def main():
    init_db(); acct=trading.get_account()
    log.info("Momentum Trader v1 PAPER ONLY | account=%s | symbols=%s",acct.status,",".join(TRADE_SYMBOLS))
    log.info("Limits: $%.0f/trade | $%.0f exposure | %d positions | %d trades/day | $%.0f daily loss",MAX_TRADE_DOLLARS,MAX_TOTAL_EXPOSURE,MAX_OPEN_POSITIONS,MAX_TRADES_PER_DAY,MAX_DAILY_REALIZED_LOSS)
    while True:
        started=time.monotonic()
        try: run_once()
        except KeyboardInterrupt: log.info("Stopped by user"); break
        except Exception: log.exception("Cycle failed")
        time.sleep(max(1,CHECK_INTERVAL_SECONDS-(time.monotonic()-started)))

if __name__=="__main__": main()
