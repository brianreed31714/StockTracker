"""Fetch research-only ZPTA DAILY Yahoo chart OHLCV with provenance and strict QA.

This is a source candidate, NOT proof of split-adjustment correctness, quote
executability, completeness, licensing, or broker access. No broker credentials.
Do not commit provider raw bars to GitHub without verifying distribution rights.

Usage:
  python analysis/zpta_daily_history_fetch.py --range 2y --output /tmp/zpta_daily.csv --metadata /tmp/zpta_daily_metadata.json
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


def extract_chart(payload, symbol="ZPTA"):
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise ValueError(f"Chart provider error: {chart['error']}")
    results = chart.get("result") or []
    if len(results) != 1:
        raise ValueError("Expected exactly one chart result")
    result = results[0]
    meta = result.get("meta") or {}
    if str(meta.get("symbol", "")).upper() != symbol.upper():
        raise ValueError("Provider returned wrong symbol")
    if str(meta.get("currency", "USD")).upper() != "USD":
        raise ValueError("Unexpected quote currency")
    timestamps = result.get("timestamp") or []
    quotes = (result.get("indicators") or {}).get("quote") or []
    if not timestamps or len(quotes) != 1:
        raise ValueError("No complete daily chart series")
    q = quotes[0]
    if any(len(q.get(k) or []) != len(timestamps) for k in ("open", "high", "low", "close", "volume")):
        raise ValueError("OHLCV length mismatch")
    zone_name = meta.get("exchangeTimezoneName") or "America/New_York"
    try:
        zone = ZoneInfo(zone_name)
    except Exception as exc:
        raise ValueError("Invalid exchange timezone") from exc
    rows = []
    seen = set()
    omitted = 0
    for i, ts in enumerate(timestamps):
        values = [q[k][i] for k in ("open", "high", "low", "close", "volume")]
        if any(v is None for v in values):
            omitted += 1
            continue
        o, h, l, c, v = [float(x) for x in values]
        if not all(math.isfinite(x) for x in (o, h, l, c, v)):
            raise ValueError("Nonfinite OHLCV")
        if min(o, h, l, c) <= 0 or v < 0 or h < max(o, c, l) or l > min(o, c):
            raise ValueError("Invalid OHLCV")
        d = datetime.fromtimestamp(int(ts), zone).date().isoformat()
        if d in seen:
            raise ValueError("Duplicate trading date")
        seen.add(d)
        rows.append({"date": d, "open": o, "high": h, "low": l,
                     "close": c, "volume": int(v)})
    rows.sort(key=lambda r: r["date"])
    if not rows:
        raise ValueError("No valid OHLCV rows")
    events = result.get("events") or {}
    split_events = list((events.get("splits") or {}).values())
    dividend_events = list((events.get("dividends") or {}).values())
    info = {
        "source": "Yahoo Finance chart public delayed research endpoint",
        "symbol": symbol.upper(),
        "exchange_timezone": zone_name,
        "rows": len(rows),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
        "missing_rows": omitted,
        "zero_volume_days": sum(r["volume"] == 0 for r in rows),
        "split_events": split_events,
        "dividend_events": dividend_events,
        "corporate_action_adjustment_independently_verified": False,
        "broker_quote_and_fill_quality_verified": False,
        "status": "SOURCE_CANDIDATE_REQUIRES_INDEPENDENT_RECONCILIATION",
    }
    return rows, info


def download_daily(symbol="ZPTA", history_range="2y"):
    if history_range not in {"1y", "2y", "5y", "max"}:
        raise ValueError("Unsupported range")
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + symbol.upper() + "?" + urlencode({
               "interval": "1d", "range": history_range, "events": "div,splits",
               "includeAdjustedClose": "true",
           }))
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 StockTracker offline daily research"})
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)
    return extract_chart(payload, symbol)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--range", default="2y", choices=["1y", "2y", "5y", "max"])
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--metadata", type=Path, required=True)
    p.add_argument("--min-sessions", type=int, default=130)
    args = p.parse_args()
    rows, info = download_daily(history_range=args.range)
    if args.min_sessions < 1:
        raise ValueError("Invalid minimum sessions")
    if len(rows) < args.min_sessions:
        raise RuntimeError(f"Only {len(rows)} sessions; need {args.min_sessions}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=["date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)
    info["retrieved_utc"] = datetime.now(timezone.utc).isoformat()
    info["csv_sha256"] = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
