#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env.config')
load_dotenv(ROOT / '.env', override=True)
ALLOWED_PREFIXES = ("analysis/proposals/", "analysis/performance/", "analysis/evidence/")

def run(*args, check=True):
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=check)

def dirty_outside_allowed():
    r = run("git", "status", "--porcelain", "--untracked-files=all")
    bad = []
    for line in r.stdout.splitlines():
        path = line[3:].replace("\\", "/")
        if path.startswith(ALLOWED_PREFIXES):
            continue
        if path.startswith("analysis/daily/"):
            continue
        bad.append(line)
    return bad

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", default="Publish StockTracker proposals and performance")
    args = ap.parse_args()

    # External reports are intentionally never added to the Git checkout.
    # Publishing is a separate, explicit operation after review.
    if os.getenv("STOCKTRACKER_RUNTIME_ROOT", "").strip():
        print("Runtime reports stored externally; automatic Git evidence publishing skipped.")
        return

    bad = dirty_outside_allowed()
    if bad:
        print("Refusing Git sync because non-analysis working files are dirty:")
        for x in bad:
            print("  " + x)
        raise SystemExit(2)

    run("git", "add", "analysis/proposals", "analysis/performance", "analysis/evidence", check=False)

    diff = run("git", "diff", "--cached", "--quiet", check=False)
    if diff.returncode == 0:
        print("No StockTracker proposal/performance changes to commit.")
        return

    run("git", "commit", "-m", args.message)

    push = run("git", "push", check=False)
    if push.returncode != 0:
        print("Initial push did not fast-forward; rebasing on origin/main...")
        rb = run("git", "pull", "--rebase", check=False)
        if rb.returncode != 0:
            print(rb.stdout)
            print(rb.stderr)
            raise SystemExit(rb.returncode)
        push = run("git", "push", check=False)

    if push.returncode != 0:
        print(push.stdout)
        print(push.stderr)
        raise SystemExit(push.returncode)

    print("StockTracker evidence, proposals, and performance pushed to GitHub.")

if __name__ == "__main__":
    main()
