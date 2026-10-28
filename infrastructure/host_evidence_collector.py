"""Read-only Windows evidence collector; does not claim in-memory attestation.

Collects disk source and dependency SHA-256, observed process identity and
creation time, and explicit provenance limitations. Never reads secrets.
"""
from __future__ import annotations
import hashlib
from pathlib import Path

def _digest(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > 8_000_000:
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None

def collect_host_evidence(root: Path, snapshot: dict, *, dependencies: tuple[str, ...]) -> dict:
    root = Path(root).resolve()
    components = snapshot.get("components") or {}
    trader = ((components.get("trader") or {}).get("process") or {})
    observed_script = trader.get("script")
    if (trader.get("state") != "OBSERVED" or
            not isinstance(observed_script, str) or
            Path(observed_script).name != observed_script or
            not observed_script.endswith(".py")):
        return {"disk_code_sha256": None, "disk_dependencies_sha256": None,
                "process_identity_observed": False, "loaded_code_verified": False,
                "loaded_dependencies_verified": False}
    code = _digest(root / observed_script)
    parts = []
    for rel in dependencies:
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            return {"disk_code_sha256": code, "disk_dependencies_sha256": None,
                    "process_identity_observed": True, "loaded_code_verified": False,
                    "loaded_dependencies_verified": False}
        value = _digest(root / rel)
        if value is None:
            return {"disk_code_sha256": code, "disk_dependencies_sha256": None,
                    "process_identity_observed": True, "loaded_code_verified": False,
                    "loaded_dependencies_verified": False}
        parts.append(rel + ":" + value)
    dep_digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return {"disk_code_sha256": code, "disk_dependencies_sha256": dep_digest,
            "process_identity_observed": True, "loaded_code_verified": False,
            "loaded_dependencies_verified": False}
