"""Independent-reader checks for sanitized Windows host status.

This verifies *claims and freshness*, not the underlying process memory.
Never promote a source-only report to loaded-runtime verification.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except ValueError:
        return None


def check_host_confirmation(status: dict, *, expected_commit: str,
                            observed_at_utc: str, max_age_seconds: int = 900) -> dict:
    """Fail closed on stale, mismatched or unsubstantiated host claims."""
    status = status if isinstance(status, dict) else {}
    reasons = []
    now = _timestamp(observed_at_utc)
    stamp = _timestamp(status.get("observed_at_utc")) if isinstance(status, dict) else None
    if now is None:
        raise ValueError("Reader clock must be an offset-aware ISO timestamp")
    if stamp is None or not 0 <= (now - stamp).total_seconds() <= max_age_seconds:
        reasons.append("HOST_STATUS_STALE_OR_MISSING")
    if not SHA40.fullmatch(expected_commit or "") or status.get("git_head") != expected_commit:
        reasons.append("EXPECTED_COMMIT_NOT_MATCHED")
    if status.get("source_code_synced") is not True:
        reasons.append("SOURCE_SYNC_UNVERIFIED")
    if status.get("processes_stable") is not True:
        reasons.append("PROCESS_HEALTH_UNVERIFIED")
    # These must be populated by a separately implemented host collector.
    # A boolean by itself is not proof of a digest.
    loaded = status.get("loaded_code_sha256")
    dependencies = status.get("loaded_dependencies_sha256")
    if not (SHA256.fullmatch(loaded or "") and
            status.get("in_memory_trader_digest_verified") is True):
        reasons.append("LOADED_CODE_DIGEST_UNVERIFIED")
    if not (SHA256.fullmatch(dependencies or "") and
            status.get("loaded_dependencies_verified") is True):
        reasons.append("LOADED_DEPENDENCIES_UNVERIFIED")
    if status.get("post_sync_eod_verified") is not True:
        reasons.append("POST_SYNC_EOD_UNVERIFIED")
    if status.get("process_recovery_verified") is not True:
        reasons.append("PROCESS_RECOVERY_UNVERIFIED")
    return {"status": "CLAIMS_COMPLETE_UNCORROBORATED" if not reasons else "UNVERIFIED",
            "reasons": reasons, "expected_commit": expected_commit}
