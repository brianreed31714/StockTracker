"""Read-only StockTracker EOD failure-evidence inventory.

Never runs the review, imports broker/model modules, prints secret values,
performs network actions, or changes files. Artifact existence is NOT
proof that a phase completed correctly.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess


def settings(path: Path) -> dict[str, str]:
    result = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            key, val = s.split("=", 1)
            if key.strip() in {"STOCKTRACKER_RUNTIME_ROOT", "OPENAI_API_KEY"}:
                result[key.strip()] = val.strip().strip("\"'")
    return result


def artifact_status(path: Path) -> dict:
    if not path.is_file():
        return {"state": "MISSING"}
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        return {"state": "PRESENT", "updated_at_utc": mtime}
    except OSError:
        return {"state": "UNREADABLE"}


def probe(root: Path, review_date: str) -> dict:
    root = root.resolve()
    values = settings(root / ".env.config")
    values.update(settings(root / ".env"))
    raw_root = (os.environ.get("STOCKTRACKER_RUNTIME_ROOT") or
                values.get("STOCKTRACKER_RUNTIME_ROOT") or "").strip()
    runtime = Path(os.path.expandvars(raw_root)).expanduser().resolve() if raw_root else root
    if runtime != root and root in runtime.parents:
        raise ValueError("Runtime root must be outside source checkout")
    state = runtime / "post_close_review_state.json"
    if not state.is_file():
        state = root / "post_close_review_state.json"
    try:
        obj = json.loads(state.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            obj = {}
    except (OSError, ValueError, TypeError):
        obj = {}
    date_matches = obj.get("review_date") == review_date
    file_defs = {
        "review_bundle": runtime / "analysis" / "daily" / review_date / "performance_input.json",
        "evidence_manifest": runtime / "analysis" / "evidence" / review_date / "manifest.json",
        "ai_review": runtime / "analysis" / "daily" / review_date / "daily_model_review.json",
        "proposal_overview": runtime / "analysis" / "proposals" / "REVIEW.md",
        "performance_latest": runtime / "analysis" / "performance" / "latest.json",
    }
    artifacts = {name: artifact_status(path) for name, path in file_defs.items()}
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            text=True, capture_output=True, timeout=15,
        )
        if result.returncode == 0:
            rows = [line[3:].replace("\\", "/") for line in result.stdout.splitlines()
                    if len(line) >= 4]
            dirty_code = sum(
                not name.startswith(("analysis/proposals/", "analysis/performance/",
                                     "analysis/evidence/", "analysis/daily/"))
                for name in rows
            )
            git = {"state": "OK", "dirty_non_analysis_paths": dirty_code,
                   "changed_analysis_paths": len(rows) - dirty_code}
        else:
            git = {"state": "UNAVAILABLE"}
    except (OSError, subprocess.TimeoutExpired):
        git = {"state": "UNAVAILABLE"}
    return {
        "review_date": review_date,
        "state_date_matches": date_matches,
        "review_status": obj.get("status") if date_matches else "UNVERIFIED",
        "attempts": obj.get("attempts") if date_matches else "UNVERIFIED",
        "failure_stage": obj.get("failure_stage") if date_matches else None,
        "failure_error_text": "REDACTED",
        "runtime_external": runtime != root,
        "openai_key_present_in_probe_context": bool(
            os.environ.get("OPENAI_API_KEY") or values.get("OPENAI_API_KEY")
        ),
        "artifacts": artifacts,
        "git": git,
        "interpretation": (
            "Artifact presence is a timestamped clue, not proof a pipeline step succeeded. "
            "The old generic FAILED state may not identify the underlying error."
        ),
        "side_effects": "NONE",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args()
    print(json.dumps(probe(args.root, args.date), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
