XOM Trading Control Center
==========================

This is a READ-ONLY Streamlit dashboard for the XOM paper-trading bot.

FILES
-----
trading_dashboard.py
requirements.txt
start_dashboard.bat

INSTALL ONCE
------------
1. Copy these files into the SAME StockTracker folder that contains:
      xom_bot.sqlite3
      xom_bot_auditable_v4_pushover.py

2. Open Command Prompt in that folder.

3. Install the dashboard packages:
      python -m pip install -r requirements.txt

RUN
---
Double-click:
      start_dashboard.bat

Or run:
      python -m streamlit run trading_dashboard.py

Your browser should open automatically, normally at:
      http://localhost:8501

IMPORTANT
---------
- The dashboard does NOT place trades.
- Keep the XOM bot running in its own process.
- The dashboard only reads xom_bot.sqlite3.
- BUY/SELL markers appear on the chart when those decision rows exist.
- Recent submitted paper orders and AI-analyzed news are displayed.
- If the database is somewhere else, change its path in the dashboard sidebar.

V2 COMPACT MODE
---------------
Optimized for half-screen browser width so XOM and CryptoTracker dashboards can sit side-by-side.
