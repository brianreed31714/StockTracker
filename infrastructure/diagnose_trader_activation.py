"""Read-only, sanitized diagnosis of a blocked StockTracker trader activation.

Run from StockTracker as:
    python -m infrastructure.diagnose_trader_activation

NO process changes, network calls, Git mutations, secrets, or raw command lines
are printed. A PID or basename alone never authorizes trader termination.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PureWindowsPath

from infrastructure.activate_review_repair import (
    ROOT, TRADER_NAME, ActivationBlocked, _trader_script_argument,
    _verified_supervisor_launch, matching_traders,
)
from infrastructure.runtime_inventory import collect, latest_launches, windows_processes

def diagnostic_report(root: Path, snapshot: dict, processes: list[dict],
                      launches: dict[int, dict]) -> dict:
    """Return only allowlisted process/provenance facts, never argv or paths."""
    trader = snapshot.get("components", {}).get("trader", {})
    observed = trader.get("process", {})
    inventory_pids = [int(pid) for pid in observed.get("pids", [])]
    expected = str((root.resolve() / TRADER_NAME)).replace("\\", "/").casefold()
    candidates = []
    for proc in processes:
        pid = int(proc.get("pid") or 0)
        raw = str(proc.get("command") or "")
        script = _trader_script_argument(raw)
        argument_name = PureWindowsPath(script).name.lower() if script else None
        contains_name = TRADER_NAME.lower() in raw.lower()
        if pid not in inventory_pids and argument_name != TRADER_NAME.lower() and not contains_name:
            continue
        launch = launches.get(pid)
        same_name = argument_name == TRADER_NAME.lower()
        full_path_match = same_name and script.replace("\\", "/").casefold() == expected
        other_absolute_path = same_name and (
            PureWindowsPath(script).is_absolute() or Path(script).is_absolute()
        ) and not full_path_match
        log_attested = _verified_supervisor_launch(proc, launch, TRADER_NAME)
        if not raw:
            role = "COMMAND_LINE_HIDDEN"
        elif not script and contains_name:
            role = "TRADER_NAME_IN_ARGUMENTS_NOT_EXECUTED_SCRIPT"
        elif not script:
            role = "COMMAND_VISIBLE_EXECUTED_SCRIPT_UNRESOLVED"
        elif full_path_match:
            role = "EXACT_TRADER_SCRIPT_PATH"
        elif other_absolute_path:
            role = "FOREIGN_ABSOLUTE_TRADER_FILENAME"
        elif same_name:
            role = "RELATIVE_TRADER_SCRIPT_NO_PATH_AUTHORITY"
        elif contains_name:
            role = "TRADER_NAME_IN_ARGUMENTS_NOT_EXECUTED_SCRIPT"
        else:
            role = "INVENTORY_PID_SCRIPT_NOT_TRADER"
        candidates.append({
            "pid": pid,
            "inventory_pid": pid in inventory_pids,
            "command_visible": bool(raw),
            "executed_script_category": role,
            "supervisor_log_entry_present": launch is not None,
            "supervisor_start_provenance_matched": log_attested,
            "has_process_start_timestamp": bool(proc.get("started_utc")),
        })
    candidates.sort(key=lambda c: (not c["inventory_pid"], c["pid"]))

    error = None
    try:
        strict = matching_traders(processes, root, launches=launches)
        strict_pids = sorted(int(p["pid"]) for p in strict)
    except ActivationBlocked as exc:
        strict_pids = []
        # This is a known non-secret message; never include raw exception values.
        error = (
            "FOREIGN_TRADER_PATH_DETECTED"
            if "outside StockTracker" in str(exc)
            else "STRICT_IDENTITY_CHECK_REJECTED"
        )
    report = {
        "mode": "READ_ONLY_NO_PROCESS_CHANGES",
        "repository": "StockTracker",
        "selected_trader_basename": TRADER_NAME,
        "inventory_state": observed.get("state", "UNAVAILABLE"),
        "inventory_identification": observed.get("identification", "UNAVAILABLE"),
        "inventory_pids": inventory_pids,
        "inventory_script_match": trader.get("script_version", {}).get("state", "UNVERIFIED"),
        "manifest_script": snapshot.get("active_manifest_files", {}).get("trader", "UNVERIFIED"),
        "strict_identity_pids": strict_pids,
        "candidate_processes": candidates,
        "strict_identity_error": error,
    }
    if len(strict_pids) == 1 and inventory_pids == strict_pids:
        report["decision"] = "IDENTITIES_AGREE"
    elif not strict_pids and any(c["inventory_pid"] for c in candidates):
        report["decision"] = "INVENTORY_PID_LACKS_STRICT_PROVENANCE"
    elif len(strict_pids) > 1:
        report["decision"] = "MULTIPLE_STRICT_TRADERS"
    elif strict_pids and inventory_pids != strict_pids:
        report["decision"] = "INVENTORY_AND_STRICT_PID_DISAGREE"
    else:
        report["decision"] = "INSUFFICIENT_PROCESS_EVIDENCE"
    return report


def main():
    if os.name != "nt":
        print("BLOCKED: This read-only diagnostic requires the Windows StockTracker PC.")
        raise SystemExit(2)
    root = ROOT.resolve()
    try:
        snapshot = collect(root)
        procs = windows_processes()
        launches = latest_launches(root / "deploy" / "state" / "supervisor.log")
        report = diagnostic_report(root, snapshot, procs, launches)
    except Exception:
        print("BLOCKED: Could not read StockTracker process evidence. No changes made.")
        raise SystemExit(2)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
