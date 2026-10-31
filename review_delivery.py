"""Date-scoped model-review delivery. No trader imports or secret persistence.

Publication and provider acceptance are separate facts. A dispatch interrupted
after its durable intent is written requires operator reconciliation: Pushover
has no client idempotency key, so automatically retrying could duplicate it.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo


def canonical_day(value):
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("Expected ISO report date")
    return value


def require_completed_crypto_day(value, now=None):
    canonical_day(value)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Aware clock required")
    if date.fromisoformat(value) >= now.astimezone(ZoneInfo("America/Los_Angeles")).date():
        raise ValueError("Crypto review requires an elapsed Pacific calendar day")


def provider_status(response):
    """HTTP success alone is insufficient; never return raw provider content."""
    try:
        body = response.json()
    except (TypeError, ValueError):
        return "UNCONFIRMED"
    if (response.status_code == 200 and isinstance(body, dict)
            and type(body.get("status")) is int and body["status"] == 1):
        return "API_ACCEPTED"
    if isinstance(body, dict) and type(body.get("status")) is int and body["status"] == 0:
        return "API_NOT_ACCEPTED"
    return "UNCONFIRMED"


def read_object(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("Expected JSON object")
    return obj


def write_object(path, obj):
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(obj, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


@contextmanager
def day_lock(state_dir, day):
    canonical_day(day)
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / (day + ".lock")).open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True,
                            text=True, encoding="utf-8", timeout=60)
    if result.returncode:
        raise RuntimeError("Publication verification failed; details withheld")
    return result.stdout.strip()


def publication_proof(root, project, day):
    """Verify dated, committed artifacts and an observed matching origin/main.

    A no-change publisher exit after an earlier failed push is NOT sufficient.
    No fetch, commit, push, pull, or rebase is performed here.
    """
    canonical_day(day)
    head = git(root, "rev-parse", "HEAD")
    if git(root, "branch", "--show-current") != "main":
        raise RuntimeError("Publication requires main")
    remote = git(root, "ls-remote", "--exit-code", "origin", "refs/heads/main").split()
    if not remote or remote[0] != head:
        raise RuntimeError("Origin/main publication is unconfirmed")
    if project == "CryptoTracker":
        require_completed_crypto_day(day)
        paths = [f"published/daily/{day}/manifest.json", "analysis/proposals/current.json"]
    elif project == "StockTracker":
        paths = [f"analysis/performance/sanitized_daily/{day}.json"]
    else:
        raise ValueError("Unexpected project")
    for path in paths:
        committed = git(root, "show", f"{head}:{path}")
        local = (Path(root) / path).read_text(encoding="utf-8").strip()
        if committed != local:
            raise RuntimeError("Publication artifact differs from committed content")
        obj = json.loads(committed)
        if obj.get("report_date", obj.get("review_date")) != day:
            raise RuntimeError("Publication date mismatch")
        if path.endswith("manifest.json") and obj.get("report_day_status") != "ELAPSED_PACIFIC_DAY_UNVERIFIED":
            raise RuntimeError("Completed-day evidence missing")
    return head


def record_publication(root, state_dir, project, day, review_path):
    with day_lock(state_dir, day):
        review_bytes = Path(review_path).read_bytes()
        if json.loads(review_bytes).get("review_date") != day:
            raise ValueError("Review date mismatch")
        commit = publication_proof(root, project, day)
        write_object(Path(state_dir) / (day + ".publication.json"), {
            "schema": "review_publication_v1", "project": project,
            "review_date": day, "review_sha256": hashlib.sha256(review_bytes).hexdigest(),
            "source_commit": commit, "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        })


def deliver_once(state_dir, project, day, review_path, send):
    with day_lock(state_dir, day):
        review_bytes = Path(review_path).read_bytes()
        digest = hashlib.sha256(review_bytes).hexdigest()
        if json.loads(review_bytes).get("review_date") != day:
            raise ValueError("Review date mismatch")
        proof = read_object(Path(state_dir) / (day + ".publication.json"))
        if (proof.get("schema") != "review_publication_v1" or proof.get("project") != project
                or proof.get("review_date") != day or proof.get("review_sha256") != digest):
            raise ValueError("Matching publication receipt required")
        receipt_path = Path(state_dir) / (day + ".notification.json")
        if receipt_path.exists():
            old = read_object(receipt_path)
            if old.get("review_date") != day or old.get("project") != project:
                raise ValueError("Invalid notification receipt")
            if old.get("review_sha256") != digest:
                raise ValueError("Review changed after a notification attempt; reconcile manually")
            status = old.get("provider_status")
            if status not in {"DISABLED", "CONFIG_MISSING"}:
                return status if status in {"API_ACCEPTED", "API_NOT_ACCEPTED", "UNCONFIRMED"} else "UNCONFIRMED"
        receipt = {"schema": "review_notification_v1", "project": project,
                   "report_type": "MODEL_REVIEW", "review_date": day,
                   "review_sha256": digest, "provider_status": "DISPATCHING",
                   "attempted_at_utc": datetime.now(timezone.utc).isoformat(),
                   "device_delivery_verified": False}
        # Persist intent BEFORE network. If interrupted, the next run cannot resend.
        write_object(receipt_path, receipt)
        try:
            status = send(json.loads(review_bytes))
        except Exception:
            status = "UNCONFIRMED"
        allowed = {"API_ACCEPTED", "API_NOT_ACCEPTED", "UNCONFIRMED", "DISABLED", "CONFIG_MISSING"}
        receipt["provider_status"] = status if status in allowed else "UNCONFIRMED"
        receipt["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_object(receipt_path, receipt)
        return receipt["provider_status"]
