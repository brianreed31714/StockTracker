"""Passive observer used ONLY inside the existing ZPTA shadow process."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

from research.zpta_opportunity_audit import capture, resolve, report

ROOT = Path(__file__).resolve().parent
STARTED = datetime.now(timezone.utc).isoformat()
SOURCE_FILES = ("zpta_research_runtime.py", "research/zpta_opportunity_audit.py", "zpta_specialist_v0_1.py")
IDENTITY = {"pid": os.getpid(), "module_loaded_at": STARTED,
            "source_hashes_at_import": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCE_FILES}}
try:
    IDENTITY["startup_source_sha"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
        timeout=5, check=True).stdout.strip()
except (OSError, subprocess.SubprocessError):
    IDENTITY["startup_source_sha"] = None


def initialize(module):
    """Prove the loaded observer initialized even while the market is closed.

    This is a local module self-report, not a market observation, price, fill
    or independent memory attestation. Do not create an opportunity here.
    """
    output = {"status": "PAPER_MODULE_INITIALIZED", "paper_only": True,
              "initialized_at": module.utc_now().isoformat(), "runtime_identity": IDENTITY,
              "market_observation_created": False, "verified_fills": 0}
    module.LOG_ROOT.mkdir(parents=True, exist_ok=True)
    target = module.LOG_ROOT / "research_startup.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(target)
    return output


def observe(module, bars, provider, features, regime, signals, score, state):
    now = module.utc_now()
    path = module.LOG_ROOT / "research.sqlite3"
    latest = bars[-1]
    limits = {"min_dollar_volume": module.MIN_DOLLAR_VOLUME_5M,
              "max_spread": module.MAX_SPREAD_PROXY_PCT, "entry_score": module.ENTRY_SCORE,
              "max_trades": module.MAX_TRADES_PER_DAY,
              "daily_loss_dollars": module.STARTING_CASH * module.MAX_DAILY_LOSS_PCT}
    context = {"entry_cutoff": module.time_at_or_after(module.NO_NEW_ENTRIES_AFTER),
               "trades_today": module.trades_today(), "realized_today": module.realized_today(),
               "position_open": bool(state.get("position")), "cash": float(state["cash"]),
               "price": latest.close}
    def record(bar):
        out = asdict(bar)
        out["ts"] = bar.ts.isoformat()
        out["provider"] = provider
        return out
    capture(path, bar=record(latest), received_at=now.isoformat(), provider=provider,
            features=features, regime=regime, scores=[asdict(s) for s in signals],
            ensemble=score, limits=limits, context=context, source_identity=IDENTITY)
    resolve(path, [record(b) for b in bars], now.isoformat())
    output = report(path)
    output["observed_at"] = now.isoformat()
    output["runtime_identity"] = IDENTITY
    target = module.LOG_ROOT / "research_latest.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(target)
    return output
