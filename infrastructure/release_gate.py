"""Fail-closed CI → merge → Windows activation → EOD delivery gate.

This module is observation-only. It cannot merge, deploy, restart or send
notifications. It produces a deterministic blocker list for event-driven
orchestrators, preserving separate source-sync and loaded-runtime states.
"""
from __future__ import annotations


def evaluate_release(*, expected_commit, checks, host, notification=None):
    reasons = []
    if not isinstance(expected_commit, str) or len(expected_commit) != 40 or any(c not in "0123456789abcdef" for c in expected_commit):
        reasons.append("EXPECTED_COMMIT_INVALID")
    checks = checks if isinstance(checks, list) else []
    if not checks:
        reasons.append("REQUIRED_CI_NOT_OBSERVED")
    elif any(not isinstance(c, dict) or c.get("conclusion") != "success" for c in checks):
        reasons.append("REQUIRED_CI_NOT_ALL_GREEN")
    host = host if isinstance(host, dict) else {}
    if host.get("git_head") != expected_commit or host.get("source_code_synced") is not True:
        reasons.append("WINDOWS_SOURCE_NOT_SYNCED")
    if host.get("processes_stable") is not True:
        reasons.append("WINDOWS_PROCESS_HEALTH_UNVERIFIED")
    if host.get("in_memory_trader_digest_verified") is not True or not host.get("loaded_code_sha256"):
        reasons.append("LOADED_CODE_UNVERIFIED")
    if host.get("loaded_dependencies_verified") is not True or not host.get("loaded_dependencies_sha256"):
        reasons.append("LOADED_DEPENDENCIES_UNVERIFIED")
    if host.get("post_sync_eod_verified") is not True:
        reasons.append("POST_DEPLOY_EOD_UNVERIFIED")
    if notification is not None and (not isinstance(notification, dict) or notification.get("provider_status") != "API_ACCEPTED"):
        reasons.append("PUSHOVER_PROVIDER_NOT_ACCEPTED")
    return {
        "status": "READY_FOR_INDEPENDENT_REVIEW" if not reasons else "BLOCKED",
        "reasons": reasons,
        "expected_commit": expected_commit,
        "source_synced": host.get("git_head") == expected_commit and host.get("source_code_synced") is True,
        "loaded_runtime_verified": not any(r in reasons for r in ("LOADED_CODE_UNVERIFIED", "LOADED_DEPENDENCIES_UNVERIFIED")),
    }
