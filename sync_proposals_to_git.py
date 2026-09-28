#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALLOWED_PREFIXES = ("analysis/proposals/", "analysis/performance/")

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

    bad = dirty_outside_allowed()
    if bad:
        print("Refusing Git sync because non-analysis working files are dirty:")
        for x in bad:
            print("  " + x)
        raise SystemExit(2)

    run("git", "add", "analysis/proposals", "analysis/performance", check=False)

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

    print("StockTracker proposals/performance pushed to GitHub.")

if __name__ == "__main__":
    main()
