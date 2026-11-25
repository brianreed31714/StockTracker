"""Causal, local-only ZPTA research. No network, broker or notification API.

Capture first receipt and revisions separately. Forward bar returns are print
observations, never executable fills. Existing runtime limits are inputs, not
new strategy settings. The fifth score is an uncalibrated research hypothesis.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
RULESET = "zpta-opportunity-v1"


def stamp(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return result.astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def dip_score(features):
    """Frozen five-feature hypothesis; never connected to maybe_trade()."""
    clip = lambda x: max(0., min(1., x))
    parts = {
        "drawdown": clip(-features["session_return"] / .10),
        "stabilization": clip(1 - abs(features["ret_3m"]) / .04),
        "liquidity": clip(features["dollar_volume_5m"] / 25000),
        "reversal": clip((features["vwap_gap"] + .02) / .04),
        "durability": clip(features["ret_5m"] / .03),
    }
    return {"score": round(20 * sum(parts.values()), 4), "components": parts,
            "mode": "RESEARCH_ONLY_UNCALIBRATED"}


def block_reasons(features, regime, score, limits, context):
    """Return ALL original entry gate reasons, even with an open position."""
    reasons = []
    tests = [
        (regime == "LIQUIDITY_DANGER", "LIQUIDITY_DANGER"),
        (features["dollar_volume_5m"] < limits["min_dollar_volume"], "DOLLAR_VOLUME"),
        (features["trade_bars_5m"] < 2, "SPARSE_TRADE_BARS"),
        (features["spread_proxy_pct"] > limits["max_spread"], "SPREAD_PROXY"),
        (score < limits["entry_score"], "ENTRY_SCORE"),
        (context["entry_cutoff"], "ENTRY_CUTOFF"),
        (context["trades_today"] >= limits["max_trades"], "DAILY_TRADE_LIMIT"),
        (context["realized_today"] <= -limits["daily_loss_dollars"], "DAILY_LOSS_LIMIT"),
        (context["position_open"], "POSITION_OPEN"),
        (context["cash"] < context["price"], "INSUFFICIENT_CASH"),
    ]
    for condition, reason in tests:
        if condition:
            reasons.append(reason)
    return reasons


def capture(path, *, bar, received_at, provider, features, regime, scores,
            ensemble, limits, context, source_identity):
    received = stamp(received_at)
    start = stamp(bar["ts"])
    values = [float(bar[k]) for k in ("open", "high", "low", "close", "volume")]
    o, h, l, c, v = values
    if (not all(math.isfinite(x) for x in values) or min(o, h, l, c) <= 0
            or v < 0 or l > min(o, c) or h < max(o, c, l)):
        raise ValueError("Invalid OHLCV")
    completed = start + timedelta(minutes=1)
    if completed > received:
        raise ValueError("Cannot evaluate an incomplete or future bar")
    reasons = block_reasons(features, regime, ensemble, limits, context)
    age = (received - completed).total_seconds()
    # Data diagnostics do not silently change the existing trading policy.
    quality = []
    if age > 60:
        quality.append("DELAYED_REFERENCE")
    if provider != "alpaca_otc":
        quality.append("DELAYED_RESEARCH_PROVIDER")
    if v == 0:
        quality.append("ZERO_BAR_VOLUME")
    quality.append("EXECUTABLE_QUOTE_UNVERIFIED")
    record = {"ruleset": RULESET, "bar": bar, "received_at": received.isoformat(),
              "provider": provider, "data_age_seconds": age, "features": features,
              "regime": regime, "scores": scores, "ensemble": ensemble,
              "dip_recovery_hunter": dip_score(features), "block_reasons": reasons,
              "quality": quality, "limits": limits, "source_identity": source_identity,
              "paper_only": True, "verified_fill": False}
    key = digest([provider, start.isoformat()])
    bar_hash = digest(bar)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.execute("PRAGMA busy_timeout=5000")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS opportunities(
              id TEXT PRIMARY KEY, bar_ts TEXT, received_at TEXT, provider TEXT,
              bar_hash TEXT, record_json TEXT);
            CREATE TABLE IF NOT EXISTS revisions(
              id TEXT, bar_hash TEXT, received_at TEXT, bar_json TEXT,
              PRIMARY KEY(id,bar_hash));
            CREATE TABLE IF NOT EXISTS outcomes(
              id TEXT, horizon TEXT, observed_at TEXT, record_json TEXT,
              PRIMARY KEY(id,horizon));
            CREATE INDEX IF NOT EXISTS opportunities_received ON opportunities(received_at);
        """)
        db.execute("INSERT OR IGNORE INTO opportunities VALUES(?,?,?,?,?,?)",
                   (key, start.isoformat(), received.isoformat(), provider, bar_hash,
                    json.dumps(record, sort_keys=True, allow_nan=False)))
        original = db.execute("SELECT bar_hash FROM opportunities WHERE id=?", (key,)).fetchone()[0]
        if original != bar_hash:
            db.execute("INSERT OR IGNORE INTO revisions VALUES(?,?,?,?)",
                       (key, bar_hash, received.isoformat(), json.dumps(bar, sort_keys=True)))
    return key


def resolve(path, bars, observed_at):
    """Score receipt+5/15/60m and next-session close; no interpolation.

    Bar timestamp is its OPEN. Use completed closes within 60s of the target.
    Next-session needs an observed 15:59 bar; early-close/gapped sessions stay
    unresolved rather than being silently scored at an arbitrary later print.
    """
    if not Path(path).exists():
        return 0
    now = stamp(observed_at)
    ordered = sorted(bars, key=lambda b: stamp(b["ts"]))
    count = 0
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        pending = db.execute("SELECT id, received_at, provider, record_json FROM opportunities "
                             "WHERE received_at>=? AND (SELECT COUNT(*) FROM outcomes o WHERE o.id=opportunities.id)<4 "
                             "ORDER BY received_at DESC LIMIT 1000",
                             ((now - timedelta(days=10)).isoformat(),)).fetchall()
        for key, created, provider, raw in pending:
            receipt = stamp(created)
            record = json.loads(raw)
            reference = float(record["bar"]["close"])
            for horizon in ("5m", "15m", "60m", "next_session"):
                if db.execute("SELECT 1 FROM outcomes WHERE id=? AND horizon=?", (key, horizon)).fetchone():
                    continue
                if horizon == "next_session":
                    possible = [b for b in ordered if stamp(b["ts"]).astimezone(NY).date() > receipt.astimezone(NY).date()
                                and stamp(b["ts"]).astimezone(NY).strftime("%H:%M") == "15:59"]
                else:
                    due = receipt + timedelta(minutes=int(horizon[:-1]))
                    possible = [b for b in ordered if due <= stamp(b["ts"]) + timedelta(minutes=1) <= due + timedelta(seconds=60)
                                and stamp(b["ts"]).astimezone(NY).date() == receipt.astimezone(NY).date()]
                possible = [b for b in possible if stamp(b["ts"]) + timedelta(minutes=1) <= now
                            and b.get("provider", provider) == provider]
                if not possible:
                    continue
                final = possible[0]
                price = float(final["close"])
                if not math.isfinite(price) or price <= 0:
                    continue
                output = {"bar_ts": final["ts"], "print_return_pct": 100 * (price / reference - 1),
                          "reference_basis": "FIRST_RECEIPT_KNOWN_BAR_CLOSE",
                          "verified_fill": False, "executable_return_pct": None}
                changed = db.execute("INSERT OR IGNORE INTO outcomes VALUES(?,?,?,?)",
                                     (key, horizon, now.isoformat(), json.dumps(output))).rowcount
                count += changed
    return count


def report(path):
    """Read-only report, suitable for private EOD artifacts; no portfolio ROI."""
    if not Path(path).exists():
        return {"status": "NO_CAPTURE_YET", "opportunities": 0}
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        total = db.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
        latest = db.execute("SELECT record_json FROM opportunities ORDER BY received_at DESC LIMIT 1").fetchone()
        record = json.loads(latest[0]) if latest else None
        counts = {}
        for field in ("block_reasons", "quality"):
            counts[field] = dict(db.execute("SELECT value,COUNT(*) FROM opportunities, "
                                           "json_each(record_json,?) GROUP BY value", ("$." + field,)))
        outcomes = db.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
        revisions = db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0]
    return {"status": "RESEARCH_CAPTURED", "ruleset": RULESET, "opportunities": total,
            "last_received_at": record["received_at"] if record else None,
            "blocked_reasons": counts["block_reasons"], "quality_counts": counts["quality"],
            "resolved_print_outcomes": outcomes, "revisions": revisions,
            "verified_fills": 0, "paper_only": True,
            "latest_source_identity": record["source_identity"] if record else None}


def liquidity_counterfactual(records, thresholds=(10000, 25000, 50000)):
    """Offline abstention sensitivity. Never assume a bid/ask or fill."""
    return {str(floor): {
        "eligible_by_turnover_only": sum(r["features"]["dollar_volume_5m"] >= floor for r in records),
        "observations": len(records), "verified_fills": 0,
        "net_executable_return_pct": None, "risk_policy_modified": False,
    } for floor in thresholds}
