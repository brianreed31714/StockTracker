#!/usr/bin/env python3
"""Recover stashed StockTracker research into an untracked, external runtime folder.

Dry run by default. Use --apply only after verifying the recovery ZIP files.
Never overwrites existing research, deletes backup files, restores the Git stash,
or changes the trading engine.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
RECOVERY = Path.home() / "Documents" / "StockTracker-Recovery"
DEST = Path.home() / "Documents" / "StockTracker-Runtime"
ENV_FILE = ROOT / ".env"
SETTING = "STOCKTRACKER_RUNTIME_ROOT"


def selected(path: str, source: str) -> bool:
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("Unsafe archive entry")
    if len(p.parts) < 3 or p.parts[0] != "analysis":
        return False
    if source == "untracked":
        return p.parts[1] in {"evidence", "proposals", "performance", "daily"}
    return path in {
        "analysis/performance/latest.json",
        "analysis/performance/latest.md",
        "analysis/proposals/REVIEW.md",
        "analysis/proposals/current.json",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Copy files and enable external runtime directory")
    args = ap.parse_args()
    if ROOT == DEST or ROOT in DEST.parents:
        raise SystemExit("Runtime destination must be outside the Git checkout")
    sources = [
        ("untracked", RECOVERY / "StockTracker-untracked-20261017.zip"),
        ("tracked", RECOVERY / "StockTracker-stash-20261017.zip"),
    ]
    for _, archive in sources:
        if not archive.is_file():
            raise SystemExit(f"Missing recovery archive: {archive}")
    existing_env = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    configured = [line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                  for line in existing_env.splitlines()
                  if line.strip().startswith(SETTING + "=")]
    if configured and any(Path(x).expanduser().resolve() != DEST.resolve() for x in configured):
        raise SystemExit("Existing runtime root differs; refusing to change configuration")

    copied = skipped = 0
    for label, archive in sources:
        with ZipFile(archive) as zf:
            for entry in zf.infolist():
                if entry.is_dir() or not selected(entry.filename, label):
                    continue
                relative = Path(*PurePosixPath(entry.filename).parts)
                dest = DEST / relative
                if dest.exists():
                    skipped += 1
                    continue
                if args.apply:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(entry) as src, dest.open("xb") as out:
                        import shutil
                        shutil.copyfileobj(src, out)
                copied += 1
    if args.apply and not configured:
        with ENV_FILE.open("a", encoding="utf-8") as handle:
            handle.write(("\n" if existing_env and not existing_env.endswith("\n") else "")
                         + f"{SETTING}={DEST}\n")
    print(f"Mode: {'APPLIED' if args.apply else 'DRY RUN'}")
    print(f"External research folder: {DEST}")
    print(f"Research files {'copied' if args.apply else 'eligible to copy'}: {copied}")
    print(f"Already existing and left untouched: {skipped}")
    print(f"Runtime setting: {'ENABLED' if args.apply else 'not changed'}")
    print("Original stash and recovery ZIPs retained; trading processes unchanged.")


if __name__ == "__main__":
    main()
