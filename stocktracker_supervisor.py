#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "deploy" / "state"
ACTIVE_MANIFEST = STATE_DIR / "active_release.json"
LOG_FILE = STATE_DIR / "supervisor.log"

load_dotenv(ROOT / ".env.config")
load_dotenv(ROOT / ".env", override=True)

CHECK_SECONDS = int(os.getenv("STOCKTRACKER_SUPERVISOR_CHECK_SECONDS", "60"))
GRACE_SECONDS = int(os.getenv("STOCKTRACKER_SUPERVISOR_RESTART_GRACE_SECONDS", "20"))
BOOT_DELAY_SECONDS = int(os.getenv("STOCKTRACKER_SUPERVISOR_BOOT_DELAY_SECONDS", "30"))
TRADER_FALLBACK = os.getenv("STOCKTRACKER_ACTIVE_TRADER", "momentum_trader_v1_4_agentic.py").strip()
GEO_FALLBACK = os.getenv("STOCKTRACKER_ACTIVE_GEO", "xom_geo_feed_v1_1_agentic.py").strip()
DASH_FALLBACK = os.getenv("STOCKTRACKER_ACTIVE_DASHBOARD", "momentum_dashboard_v1_3_agentic.py").strip()
AGENT = "stocktracker_deployment_agent.py"

PUSH_TOKEN = (os.getenv("PUSHOVER_STOCK_AGENTIC_TOKEN", "").strip() or os.getenv("PUSHOVER_API_TOKEN", "").strip())
PUSH_USER = (os.getenv("PUSHOVER_STOCK_AGENTIC_GROUP_KEY", "").strip() or os.getenv("PUSHOVER_USER_KEY", "").strip())

def log(msg):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} | {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def push(title, message):
    if not PUSH_TOKEN or not PUSH_USER:
        return
    try:
        requests.post("https://api.pushover.net/1/messages.json", data={"token":PUSH_TOKEN,"user":PUSH_USER,"title":title,"message":message[:1024]}, timeout=20)
    except Exception:
        pass

def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def active_files():
    manifest = load_json(ACTIVE_MANIFEST)
    files = dict(manifest.get("files") or {})
    resolved = {
        "trader": files.get("trader") or TRADER_FALLBACK,
        "geo_feed": files.get("geo_feed") or GEO_FALLBACK,
        "dashboard": files.get("dashboard") or DASH_FALLBACK,
    }

    # Seed local deployment state on the first supervisor run. This lets the
    # first future deployment stop/replace the baseline processes cleanly.
    if not manifest:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        baseline = {
            "proposal_id": "BASELINE",
            "commit": "",
            "deployed_at": datetime.now().isoformat(timespec="seconds"),
            "files": resolved,
            "pids": {},
        }
        ACTIVE_MANIFEST.write_text(json.dumps(baseline, indent=2), encoding="utf-8")

    return resolved

def command_lines():
    ps = "Get-CimInstance Win32_Process | Where-Object {$_.CommandLine} | Select-Object -ExpandProperty CommandLine"
    r = subprocess.run(["powershell","-NoProfile","-Command",ps], text=True, capture_output=True)
    return [x.strip() for x in r.stdout.splitlines() if x.strip()] if r.returncode == 0 else []

def running(rel):
    marker = Path(rel).name.lower()
    return any(marker in line.lower() for line in command_lines())

def start(rel, dashboard=False):
    path = (ROOT / rel).resolve()
    if not path.exists():
        raise FileNotFoundError(rel)
    cmd = [sys.executable, "-m", "streamlit", "run", str(path)] if dashboard else [sys.executable, str(path)]
    flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    return subprocess.Popen(cmd, cwd=ROOT, creationflags=flags).pid

def ensure(name, rel, dashboard=False):
    if running(rel):
        return "RUNNING"
    log(f"{name} missing; waiting {GRACE_SECONDS}s")
    time.sleep(GRACE_SECONDS)
    if running(rel):
        return "RUNNING"
    pid = start(rel, dashboard)
    log(f"Started {name}: {rel} pid={pid}")
    return f"STARTED pid={pid}"

def cycle(notify=False):
    files = active_files()
    status = {}
    status["Deployment Agent"] = ensure("Deployment Agent", AGENT)
    status["Trader"] = ensure("Trader", files["trader"])
    status["Geo Feed"] = ensure("Geo Feed", files["geo_feed"])
    status["Dashboard"] = ensure("Dashboard", files["dashboard"], True)
    if notify:
        lines = ["StockTracker supervisor online.", f"Trader: {files['trader']}", f"Geo: {files['geo_feed']}", f"Dashboard: {files['dashboard']}"]
        lines += [f"{k}: {v}" for k, v in status.items()]
        push("StockTracker Startup", "\n".join(lines))

def main():
    log(f"Supervisor starting; boot delay {BOOT_DELAY_SECONDS}s")
    time.sleep(max(0, BOOT_DELAY_SECONDS))
    try:
        cycle(True)
    except Exception as exc:
        log(f"Initial startup error: {exc}")
        push("StockTracker Startup FAILED", str(exc))
    while True:
        try:
            cycle(False)
        except Exception as exc:
            log(f"Supervisor cycle error: {exc}")
        time.sleep(max(15, CHECK_SECONDS))

if __name__ == "__main__":
    main()
