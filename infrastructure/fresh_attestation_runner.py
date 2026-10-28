"""Launch the Windows host attestation in a fresh, bounded Python process.

A long-running deployment agent otherwise caches the imported attestation
module across Git fast-forwards. A fresh subprocess observes the CURRENT disk
module on every scan without restarting the trader or any other service.
The returned JSON is a host claim, not proof of loaded trader memory.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

VALID_STATES = frozenset({
    "UNVERIFIED", "CODE_SYNCED_RUNTIME_UNVERIFIED",
    "CODE_SYNCED_PROCESS_OBSERVED", "HOST_PROCESSES_STABLE_SOURCE_ONLY",
    "EOD_EXECUTION_VERIFIED",
})


def run_fresh_host_attestation(root: Path, *, timeout_seconds: int = 150) -> dict:
    if not 10 <= timeout_seconds <= 300:
        raise ValueError("Invalid bounded attestation timeout")
    root = Path(root).resolve()
    # Fixed module/arguments only: no shell, no Git-controlled command.
    command = [sys.executable, "-m", "infrastructure.windows_activation_attestation",
               "--root", str(root), "--notify"]
    try:
        proc = subprocess.run(
            command, cwd=root, capture_output=True, text=True, check=False,
            timeout=timeout_seconds,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "UNVERIFIED", "reason": "HOST_ATTESTATION_PROCESS_UNAVAILABLE"}
    try:
        receipt = json.loads(proc.stdout)
    except (ValueError, TypeError):
        return {"status": "UNVERIFIED", "reason": "HOST_ATTESTATION_RECEIPT_INVALID"}
    if (proc.returncode != 0 or not isinstance(receipt, dict)
            or receipt.get("state") not in VALID_STATES):
        return {"status": "UNVERIFIED", "reason": "HOST_ATTESTATION_REPORTED_FAILURE"}
    return {
        "status": "HOST_CLAIM_ONLY",
        "state": receipt["state"],
        "remote_publish": receipt.get("remote_publish", "UNCONFIRMED"),
        # Never claim loaded code, dependencies or device delivery from this.
        "loaded_runtime_verified": False,
    }
