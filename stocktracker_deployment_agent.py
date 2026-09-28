#!/usr/bin/env python3
"""
StockTracker local deployment agent.

Runs on the Windows trading PC. It polls the private Git repo for an approved
deployment request written by ChatGPT/Codex. It can only deploy allowlisted
StockTracker components and never executes arbitrary shell commands from Git.

Expected request:
  deploy/requests/P-STOCK-YYYYMMDD-NN.json

Example:
{
  "proposal_id": "P-20260926-01",
  "status": "READY_TO_DEPLOY",
  "commit": "<full-or-short-git-sha>",
  "components": ["trader", "smart_money", "dashboard"],
  "files": {
    "trader": "auto_trader_with_alerts_v11_8_3.py",
    "smart_money": "SmartMoneyMonitor/smart_money_monitor_v2_3.py",
    "dashboard": "cryptotracker_dashboard_v11_8_3.py"
  }
}

Security model:
- exact allowlisted component names only
- Python files must stay inside the repo
- no arbitrary command fields are honored
- py_compile before activation
- Git commit must exist locally
- previous active manifest is kept for rollback
"""

from __future__ import annotations

import json
import os
import py_compile
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DEPLOY_DIR = ROOT / "deploy"
REQUEST_DIR = DEPLOY_DIR / "requests"
STATE_DIR = DEPLOY_DIR / "state"
ACTIVE_MANIFEST = STATE_DIR / "active_release.json"
PREVIOUS_MANIFEST = STATE_DIR / "previous_release.json"
PROCESSED_REQUESTS = STATE_DIR / "processed_requests.json"
LOG_FILE = STATE_DIR / "deployment_agent.log"

load_dotenv(ROOT / ".env.config")
load_dotenv(ROOT / ".env", override=True)

POLL_SECONDS = int(os.getenv("STOCKTRACKER_DEPLOYMENT_AGENT_POLL_SECONDS", "60"))
AUTO_DEPLOY = os.getenv("STOCKTRACKER_DEPLOYMENT_AGENT_ENABLED", "1").strip().lower() not in {"0","false","no"}

PUSH_TOKEN = (
    os.getenv("PUSHOVER_STOCK_AGENTIC_TOKEN", "").strip()
    or os.getenv("PUSHOVER_API_TOKEN", "").strip()
)
PUSH_USER = (
    os.getenv("PUSHOVER_STOCK_AGENTIC_GROUP_KEY", "").strip()
    or os.getenv("PUSHOVER_USER_KEY", "").strip()
)

ALLOWED_COMPONENTS = {"trader", "geo_feed", "dashboard"}
ALLOWED_PREFIXES = {
    "trader": ("momentum_trader_",),
    "geo_feed": ("xom_geo_feed",),
    "dashboard": ("momentum_dashboard_",),
}

# Capabilities that must survive every future deployment unless the guard
# itself is deliberately changed in an approved release.
PROTECTED_CAPABILITIES = {
    "trader": {
        "required": (
            "PAPER_ONLY = True",
            "paper=True",
            ".env.config",
            "ALPACA_DATA_FEED",
            "MAX_DAILY_REALIZED_LOSS",
            "PUSHOVER_STOCK_EOD",
            "def geo_snapshot",
            "CREATE TABLE IF NOT EXISTS decision_funnel",
            "REGIME_SHADOW_ENABLED",
            "CREATE TABLE IF NOT EXISTS market_regime_shadow",
        ),
        "forbidden": (
            "PAPER_ONLY = False",
            "paper=False",
        ),
    },
    "geo_feed": {
        "required": (
            ".env.config",
            "OPENAI_API_KEY",
            "GEO_MIN_MATERIALITY",
            "atomic_json",
        ),
        "forbidden": (
            "TradingClient(",
            "submit_order(",
        ),
    },
    "dashboard": {
        "required": (
            ".env.config",
            "streamlit",
            "READ ONLY",
        ),
        "forbidden": (
            "TradingClient(",
            "submit_order(",
        ),
    },
}


def log(msg: str):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} | {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def push(title: str, message: str):
    if not PUSH_TOKEN or not PUSH_USER:
        return
    try:
        requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": PUSH_TOKEN, "user": PUSH_USER, "title": title, "message": message[:1024]},
            timeout=20,
        )
    except Exception:
        pass


def run(*args: str, check=True):
    return subprocess.run(
        list(args), cwd=ROOT, text=True, capture_output=True, check=check
    )


def safe_rel(component: str, rel: str) -> Path:
    if component not in ALLOWED_COMPONENTS:
        raise ValueError(f"Component not allowlisted: {component}")

    rel = str(rel).replace("\\", "/")
    if rel.startswith("/") or ".." in Path(rel).parts:
        raise ValueError(f"Unsafe path: {rel}")

    if not rel.endswith(".py"):
        raise ValueError(f"Only Python files may be activated: {rel}")

    if not any(rel.startswith(prefix) for prefix in ALLOWED_PREFIXES[component]):
        raise ValueError(f"File is not valid for {component}: {rel}")

    path = (ROOT / rel).resolve()
    if ROOT.resolve() not in path.parents:
        raise ValueError(f"File escapes repository: {rel}")
    if not path.exists():
        raise FileNotFoundError(rel)
    return path


def validate_component_capabilities(component: str, path: Path):
    source = path.read_text(encoding="utf-8", errors="replace")
    rules = PROTECTED_CAPABILITIES[component]
    missing = [marker for marker in rules["required"] if marker not in source]
    forbidden = [marker for marker in rules["forbidden"] if marker in source]

    if missing or forbidden:
        raise ValueError(
            f"{component} regression guard failed; "
            f"missing={missing}; forbidden={forbidden}"
        )


def validate_release_blob(commit: str, rel: str):
    """Refuse deployment if the approved file changed after the request commit."""
    requested = run("git", "rev-parse", f"{commit}:{rel}", check=False)
    current = run("git", "rev-parse", f"HEAD:{rel}", check=False)
    if requested.returncode != 0 or current.returncode != 0:
        raise ValueError(f"Could not resolve release file blob: {rel}")
    if requested.stdout.strip() != current.stdout.strip():
        raise ValueError(
            f"{rel} changed after approved commit {commit}; "
            "create a new deployment request for the current file."
        )


def validate_request(req: dict):
    if req.get("status") != "READY_TO_DEPLOY":
        raise ValueError("Request is not READY_TO_DEPLOY.")

    pid = str(req.get("proposal_id") or "")
    if not pid.startswith("P-STOCK-"):
        raise ValueError("Invalid proposal_id.")

    commit = str(req.get("commit") or "").strip()
    if not commit:
        raise ValueError("Missing commit.")
    if run("git", "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode != 0:
        raise ValueError(f"Unknown commit: {commit}")

    comps = req.get("components") or []
    files = req.get("files") or {}
    if not comps:
        raise ValueError("No components requested.")

    validated = {}
    for comp in comps:
        rel = str(files.get(comp, "")).replace("\\", "/")
        validated[comp] = safe_rel(comp, rel)
        validate_component_capabilities(comp, validated[comp])
        py_compile.compile(str(validated[comp]), doraise=True)
        validate_release_blob(commit, rel)

    return pid, commit, validated


def pull_repo():
    # Do not merge dirty local code.
    dirty = run("git", "status", "--porcelain", "--untracked-files=all").stdout.strip()
    if dirty:
        raise RuntimeError("Local repo has uncommitted changes; deployment halted.")
    run("git", "fetch", "--all")
    run("git", "pull", "--ff-only")


def taskkill_for_script(script_name: str):
    # PowerShell is used only with our locally constructed exact filename.
    escaped = script_name.replace("'", "''")
    cmd = (
        "$p=Get-CimInstance Win32_Process | "
        f"Where-Object {{$_.CommandLine -like '*{escaped}*' -and $_.ProcessId -ne $PID}}; "
        "$p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], cwd=ROOT)


def start_component(component: str, path: Path):
    rel = str(path.relative_to(ROOT))
    if component == "dashboard":
        cmd = [sys.executable, "-m", "streamlit", "run", rel]
    else:
        cmd = [sys.executable, rel]

    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP

    return subprocess.Popen(cmd, cwd=ROOT, creationflags=flags)


def save_manifest(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_manifest(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def stop_active(manifest: dict):
    for comp, rel in (manifest.get("files") or {}).items():
        if comp in ALLOWED_COMPONENTS and rel:
            taskkill_for_script(Path(rel).name)


def processed_requests():
    data = load_manifest(PROCESSED_REQUESTS)
    return data if isinstance(data, dict) else {}


def mark_processed(proposal_id: str, status: str, **extra):
    data = processed_requests()
    data[proposal_id] = {
        "status": status,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        **extra,
    }
    save_manifest(PROCESSED_REQUESTS, data)


def deploy(req_path: Path, req: dict):
    old = load_manifest(ACTIVE_MANIFEST)
    pid, commit, validated = validate_request(req)

    log(f"{pid}: validation passed at commit {commit}")
    stop_active(old)

    started = []
    try:
        for comp, path in validated.items():
            proc = start_component(comp, path)
            started.append((comp, proc))
            log(f"{pid}: started {comp} pid={proc.pid}")
            time.sleep(2)
            if proc.poll() is not None:
                raise RuntimeError(f"{comp} exited immediately with code {proc.returncode}")

        if old:
            save_manifest(PREVIOUS_MANIFEST, old)

        active = {
            "proposal_id": pid,
            "commit": commit,
            "deployed_at": datetime.now().isoformat(timespec="seconds"),
            "files": {c: str(p.relative_to(ROOT)).replace("\\","/") for c,p in validated.items()},
            "pids": {c: p.pid for c,p in started},
        }
        save_manifest(ACTIVE_MANIFEST, active)

        # Never mutate the Git-tracked deployment request locally. Doing so
        # dirties the repo and blocks the next git pull. Record local lifecycle
        # state under deploy/state instead.
        mark_processed(
            pid,
            "DEPLOYED",
            commit=commit,
            deployed_at=active["deployed_at"],
        )
        log(f"{pid}: deployment successful")
        push("StockTracker Deployment", f"{pid} deployed successfully.\nCommit {commit[:10]}")
        return True

    except Exception as exc:
        log(f"{pid}: deployment FAILED: {exc}")
        for _, proc in started:
            try: proc.terminate()
            except Exception: pass

        # Best-effort rollback to previous known active scripts.
        if old:
            try:
                for comp, rel in (old.get("files") or {}).items():
                    path = safe_rel(comp, rel)
                    start_component(comp, path)
                save_manifest(ACTIVE_MANIFEST, old)
                req["status"] = "ROLLED_BACK"
                log(f"{pid}: rolled back to previous release")
            except Exception as rollback_exc:
                req["status"] = "FAILED"
                req["rollback_error"] = str(rollback_exc)
                log(f"{pid}: rollback FAILED: {rollback_exc}")
        else:
            req["status"] = "FAILED"

        mark_processed(
            pid,
            req.get("status", "FAILED"),
            commit=commit,
            error=str(exc),
        )
        push("StockTracker Deployment FAILED", f"{pid}: {exc}")
        return False


def scan_once():
    if not AUTO_DEPLOY:
        return
    REQUEST_DIR.mkdir(parents=True, exist_ok=True)
    pull_repo()
    for path in sorted(REQUEST_DIR.glob("P-STOCK-*.json")):
        try:
            req = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if req.get("status") == "READY_TO_DEPLOY":
            pid = str(req.get("proposal_id") or "")
            done = processed_requests().get(pid)
            if done and done.get("status") in {"DEPLOYED", "ROLLED_BACK"}:
                continue

            # Migration guard for deployments completed by the older agent,
            # which marked the tracked request file locally instead of using
            # deploy/state. If the active manifest already matches this exact
            # proposal+commit, treat it as processed and do not redeploy it.
            active = load_manifest(ACTIVE_MANIFEST)
            if (
                active.get("proposal_id") == pid
                and str(active.get("commit") or "") == str(req.get("commit") or "")
            ):
                mark_processed(
                    pid,
                    "DEPLOYED",
                    commit=req.get("commit"),
                    migrated_from_active_manifest=True,
                )
                continue

            deploy(path, req)


def main():
    log("Deployment agent started.")
    push("StockTracker Deployment Agent", "Local deployment agent is running.")
    while True:
        try:
            scan_once()
        except Exception as exc:
            log(f"scan error: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
