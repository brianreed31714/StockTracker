"""Project-scoped Windows process discovery and controlled service cleanup."""
from __future__ import annotations
import json
import os
import subprocess
import time
from pathlib import Path

def _processes():
    if os.name != "nt":
        raise RuntimeError("Controlled restart requires Windows process inspection")
    ps = ("Get-CimInstance Win32_Process | "
          "Where-Object { $_.Name -match '^(python|pythonw)(\\.exe)?$' } | "
          "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell","-NoProfile","-Command",ps],capture_output=True,text=True,timeout=25)
    if r.returncode:
        raise RuntimeError("Process inspection failed: " + r.stderr[:200])
    value = json.loads(r.stdout or "null")
    return value if isinstance(value,list) else ([value] if value else [])

def _matches(command, patterns):
    import re
    # Match exact versioned Python basenames, not arbitrary path substrings.
    return any(re.search(r"(?i)(?<![\w.])"+pattern+r"(?![\w.])",command) for pattern in patterns)

def project_services(project):
    patterns = ({
        "stock": [r"momentum_trader_v[\w.\-]*\.py",r"xom_geo_feed_v[\w.\-]*\.py",r"momentum_dashboard_v[\w.\-]*\.py"],
        "crypto": [r"auto_trader_with_alerts_v[\w.\-]*\.py",r"cryptotracker_dashboard_v[\w.\-]*\.py",r"smart_money_monitor_v[\w.\-]*\.py"]
    })[project]
    return [(int(p["ProcessId"]),p.get("CommandLine") or "") for p in _processes()
            if p.get("CommandLine") and _matches(p["CommandLine"],patterns)]

def stop_project_services(project, exclude=()):
    exclude = {int(x) for x in exclude} | {os.getpid()}
    targets = [(pid,cmd) for pid,cmd in project_services(project) if pid not in exclude]
    for pid,_ in targets:
        r = subprocess.run(["taskkill","/PID",str(pid),"/T","/F"],capture_output=True,text=True,timeout=20)
        if r.returncode and any(pid == p for p,_ in project_services(project)):
            raise RuntimeError(f"Could not stop {project} service PID {pid}")
    deadline = time.monotonic()+20
    while time.monotonic()<deadline:
        remaining = [(p,c) for p,c in project_services(project) if p not in exclude]
        if not remaining:
            return [pid for pid,_ in targets]
        time.sleep(0.5)
    raise RuntimeError(f"{project} processes remain after cleanup: {[p for p,_ in remaining]}")
