"""Compact read-only Streamlit dashboard for the agentic StockTracker release."""
import json, os, sqlite3, time
from pathlib import Path
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from zpta_dashboard_support import (all_time_resolved_forecasts, daily_resolved_forecasts,
                                    explain_zpta_status, latest_observation,
                                    market_timestamp_label)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env.config")
load_dotenv(BASE_DIR / ".env", override=True)

def project_path(env_name, default_name):
    raw = os.getenv(env_name, "").strip()
    p = Path(raw).expanduser() if raw else (BASE_DIR / default_name)
    return p if p.is_absolute() else (BASE_DIR / p)

STATE=project_path("DASHBOARD_STATE_PATH","dashboard_state.json")
DB=project_path("MULTI_DB_PATH","momentum_trader.sqlite3")

st.set_page_config(page_title="Momentum Trader",page_icon="📈",layout="wide",initial_sidebar_state="collapsed")
st.markdown("""<style>
.block-container{padding-top:.7rem;padding-bottom:.5rem;max-width:1500px}.app-title{font-size:1.65rem;font-weight:750;line-height:1.05}.subtle{opacity:.65;font-size:.78rem}.pill{display:inline-block;padding:.18rem .55rem;border:1px solid rgba(128,128,128,.35);border-radius:999px;font-size:.72rem}.stMetric{border:1px solid rgba(128,128,128,.18);padding:.35rem .55rem;border-radius:.55rem}div[data-testid="stMetricValue"]{font-size:1.25rem}div[data-testid="stMetricLabel"]{font-size:.72rem}.compact{font-size:.78rem}
</style>""",unsafe_allow_html=True)

with st.sidebar:
    refresh=st.select_slider("Refresh seconds",[2,5,10,15,30,60],value=5)
    st.caption("READ ONLY — dashboard cannot place trades.")

h1,h2=st.columns([5,1])
with h1:
    st.markdown('<div class="app-title">Momentum Trader</div>',unsafe_allow_html=True)
    st.markdown('<div class="subtle">XOM • WMT • AMZN • AAPL • NVDA • TSLA • NBIS • SPY • QQQ • GLD &nbsp; | &nbsp; ZPTA shadow specialist</div>',unsafe_allow_html=True)
with h2: st.markdown('<span class="pill">PAPER ONLY</span>',unsafe_allow_html=True)

try: state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
except Exception: state={}

age=None
if state.get("generated_at"):
    try: age=max(0,(pd.Timestamp.now(tz="UTC")-pd.Timestamp(state["generated_at"])).total_seconds())
    except Exception: pass
status="LIVE" if age is not None and age<150 else ("DELAYED" if age is not None and age<600 else "STALE / NO DATA")
st.caption(f"● {status}" + (f" • updated {age:.0f}s ago" if age is not None else "") + f" • market {'OPEN' if state.get('market_open') else 'CLOSED'}")

v=state.get("vix",{}); p=state.get("portfolio",{}); g=state.get("geo",{})
a,b,c,d,e,f=st.columns(6)
a.metric("VIX",f"{v.get('level'):.2f}" if isinstance(v.get('level'),(int,float)) else v.get('source','—'))
b.metric("VIX 15m",f"{100*v.get('change_15m',0):+.2f}%")
c.metric("Exposure",f"${p.get('exposure',0):,.0f}")
d.metric("Positions",f"{p.get('open_positions',0)}")
e.metric("Realized Today",f"${p.get('realized_today',0):+,.2f}")
f.metric("Trades Today",f"{p.get('trades_today',0)}")

signals=pd.DataFrame(state.get("signals",[]))
if signals.empty:
    st.warning(f"No signal state found at {STATE}. Start momentum_trader_v1_2.py and confirm it logs the same Dashboard state path.")
else:
    for col in ["price","score","technical","context","vix_adjustment","geo_adjustment","momentum_5m","momentum_15m","rsi14","volume_ratio","unrealized_pl"]:
        if col in signals: signals[col]=pd.to_numeric(signals[col],errors="coerce")
    signals=signals.sort_values("score",ascending=False)
    show=signals.copy()
    show["Price"]=show["price"].map(lambda x:f"${x:,.2f}")
    show["Score"]=show["score"].map(lambda x:f"{x:.1f}")
    show["5m"]=show["momentum_5m"].map(lambda x:f"{x*100:+.2f}%")
    show["15m"]=show["momentum_15m"].map(lambda x:f"{x*100:+.2f}%")
    show["RSI"]=show["rsi14"].map(lambda x:f"{x:.1f}")
    show["Vol"]=show["volume_ratio"].map(lambda x:f"{x:.2f}x")
    show["Context"]=show["context"].map(lambda x:f"{x:+.1f}")
    show["VIX Adj"]=show["vix_adjustment"].map(lambda x:f"{x:+.1f}")
    show["Geo Adj"]=show["geo_adjustment"].map(lambda x:f"{x:+.1f}")
    show["P/L"]=show["unrealized_pl"].map(lambda x:f"${x:+,.2f}")
    show["Pos"]=show["position"].map(lambda x:"YES" if x else "—")
    st.dataframe(show[["symbol","Price","Score","decision","5m","15m","RSI","Vol","Context","VIX Adj","Geo Adj","Pos","P/L","reason"]],hide_index=True,use_container_width=True,height=355,
                 column_config={"symbol":"Asset","decision":"Action","reason":"Reason"})

    left,right=st.columns([1.2,1])
    with left:
        st.subheader("Scores")
        chart=signals.set_index("symbol")[["score"]]
        st.bar_chart(chart,height=220)
    with right:
        st.subheader("Open Positions")
        pos=pd.DataFrame(state.get("positions",[]))
        if pos.empty: st.info("No open positions")
        else:
            cols=[c for c in ["symbol","qty","avg_entry_price","current_price","market_value","unrealized_pl"] if c in pos]
            st.dataframe(pos[cols],hide_index=True,use_container_width=True,height=220)

st.caption(f"Geo feed: {g.get('status','—')} • active events: {g.get('active_event_count',0)} • XOM geo adjustment: {g.get('score_adjustment',0):+.1f}")

st.subheader("ZPTA Specialist — Shadow Only")
z=state.get("zpta_shadow",{}) or {}
za,zb,zc,zd,ze=st.columns(5)
za.metric("Status",str(z.get("status","—")))
zb.metric("Price",f"${float(z.get('price')):.4f}" if isinstance(z.get('price'),(int,float)) else "—")
zc.metric("Ensemble",f"{float(z.get('ensemble_score')):.1f}" if isinstance(z.get('ensemble_score'),(int,float)) else "—")
zd.metric("Action",str(z.get("action","—")))
ze.metric("Shadow Equity",f"${float(z.get('equity')):,.2f}" if isinstance(z.get('equity'),(int,float)) else "—")
st.caption(f"Provider: {z.get('provider','—')} • Regime: {z.get('regime','—')} • no broker orders")

zpta_issue=explain_zpta_status(z)
if zpta_issue:
    st.warning(zpta_issue)
    st.caption("ZPTA error reflects the last trader snapshot, not the health of historical forecasts. The specialist remains SHADOW ONLY.")

zsignals=pd.DataFrame(z.get("signals",[]) or [])
if not zsignals.empty:
    if "score" in zsignals: zsignals["score"]=pd.to_numeric(zsignals["score"],errors="coerce").round(1)
    st.dataframe(zsignals[[c for c in ["model","direction","score","reason"] if c in zsignals]],hide_index=True,use_container_width=True,height=175)

if DB.exists():
    try:
        last_zpta=latest_observation(DB)
        daily_zstats=daily_resolved_forecasts(DB)
        lifetime_zstats=all_time_resolved_forecasts(DB)
        if last_zpta:
            last_price=last_zpta.get("price")
            price_text=f"${float(last_price):.4f}" if isinstance(last_price,(int,float)) else "unavailable"
            st.caption(
                f"Last stored ZPTA quote (historical, not live): {price_text} • "
                f"{market_timestamp_label(last_zpta.get('ts'))} • "
                f"source: {last_zpta.get('provider') or 'unknown'}"
            )
        if daily_zstats:
            st.caption("Resolved ZPTA forecast performance • dates are forecast resolution dates in Eastern Time")
            daily_tab,all_time_tab=st.tabs(["Daily detail (ET)","All-time summary"])
            with daily_tab:
                dated=pd.DataFrame(daily_zstats).rename(columns={
                    "market_date":"Date (ET)", "model":"Model",
                    "horizon_minutes":"Horizon (min)", "samples":"Samples",
                    "accuracy_pct":"Accuracy (%)", "avg_return_pct":"Avg return (%)",
                })
                st.dataframe(dated,hide_index=True,use_container_width=True,height=260)
                if len(daily_zstats)>=300:
                    st.caption("Displaying 300 most recent date/model/horizon groups; the averages include every stored forecast in each group.")
            with all_time_tab:
                lifetime=pd.DataFrame(lifetime_zstats).rename(columns={
                    "model":"Model", "horizon_minutes":"Horizon (min)",
                    "samples":"Samples", "accuracy_pct":"Accuracy (%)",
                    "avg_return_pct":"Avg return (%)",
                })
                st.dataframe(lifetime,hide_index=True,use_container_width=True,height=260)
        else:
            st.caption("No resolved ZPTA forecasts are stored yet.")
    except (sqlite3.Error, OSError, ValueError):
        st.caption("ZPTA forecast history is temporarily unavailable; the historical database could not be read.")
else:
    st.caption("No ZPTA forecast database is available yet.")

st.subheader("Recent Paper Orders")
if DB.exists():
    try:
        with sqlite3.connect(DB) as c: orders=pd.read_sql_query("SELECT ts,symbol,side,notional,price,reason FROM orders ORDER BY ts DESC LIMIT 12",c)
        if orders.empty: st.caption("No orders yet.")
        else: st.dataframe(orders,hide_index=True,use_container_width=True,height=210)
    except Exception as ex: st.caption(f"Order history unavailable: {ex}")
else: st.caption("Database not created yet.")

time.sleep(refresh); st.rerun()
