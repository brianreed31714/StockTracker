#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DAILY_DIR = ROOT / "analysis" / "daily"
PROPOSAL_DIR = ROOT / "analysis" / "proposals"

def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def proposal_path(proposal_id: str):
    return PROPOSAL_DIR / f"{proposal_id}.json"

def normalize(raw: dict, review_date: str, proposal_id: str):
    q = dict(raw)
    q["proposal_id"] = proposal_id
    q.setdefault("title", "")
    q.setdefault("change_type", "RESEARCH")
    q.setdefault("target", "")
    q.setdefault("current", "")
    q.setdefault("proposed", "")
    q.setdefault("evidence", [])
    q.setdefault("risk", "")
    q.setdefault("confidence", "LOW")
    q.setdefault("recommended_mode", "SHADOW")
    q.setdefault("approval_required", True)
    q.setdefault("status", "PENDING")
    q["review_date"] = review_date
    q.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    q["updated_at"] = datetime.now().isoformat(timespec="seconds")
    q.setdefault("implementation", {})
    q.setdefault("deployment", {})
    return q

def build_review_markdown(review_date: str, proposals: list[dict]):
    lines = [
        f"# StockTracker Proposals — {review_date}",
        "",
        "Paper-trading model improvement proposals. Human approval is required before implementation/deployment.",
        "",
    ]
    if not proposals:
        lines += ["No proposals were generated.", "", "`Review today's StockTracker proposals`", ""]
        return "\n".join(lines)

    for p in proposals:
        pid = p["proposal_id"]
        lines += [
            f"## {pid} — {p.get('title','Untitled proposal')}",
            "",
            f"- **Status:** {p.get('status','PENDING')}",
            f"- **Type:** {p.get('change_type','RESEARCH')}",
            f"- **Target:** {p.get('target','')}",
            f"- **Current:** {p.get('current','')}",
            f"- **Proposed:** {p.get('proposed','')}",
            f"- **Confidence:** {p.get('confidence','LOW')}",
            f"- **Recommended mode:** {p.get('recommended_mode','SHADOW')}",
            f"- **Risk:** {p.get('risk','')}",
            "- **Evidence:**",
        ]
        ev = p.get("evidence") or []
        if ev:
            for x in ev:
                lines.append(f"  - {x}")
        else:
            lines.append("  - No evidence text supplied.")
        lines += [
            "",
            "**Approve in ChatGPT:**",
            "",
            f"`Approve {pid}`",
            "",
            "**Decline in ChatGPT:**",
            "",
            f"`Decline {pid}`",
            "",
            "---",
            "",
        ]
    lines += ["## Quick command", "", "`Review today's StockTracker proposals`", ""]
    return "\n".join(lines)

def rebuild_current(review_date: str, proposals: list[dict]):
    PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)
    current = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "review_date": review_date,
        "proposal_count": len(proposals),
        "pending": [p["proposal_id"] for p in proposals if p.get("status") == "PENDING"],
        "proposals": [
            {
                "proposal_id": p["proposal_id"],
                "title": p.get("title"),
                "confidence": p.get("confidence"),
                "recommended_mode": p.get("recommended_mode"),
                "status": p.get("status"),
            }
            for p in proposals
        ],
    }
    save_json(PROPOSAL_DIR / "current.json", current)
    (PROPOSAL_DIR / "REVIEW.md").write_text(
        build_review_markdown(review_date, proposals),
        encoding="utf-8",
    )

def publish(review_date: str):
    review_path = DAILY_DIR / review_date / "daily_model_review.json"
    review = load_json(review_path)
    if not isinstance(review, dict):
        raise FileNotFoundError(f"Review not found: {review_path}")

    published = []
    compact_date = review_date.replace("-", "")
    for i, raw in enumerate(review.get("proposals") or [], 1):
        pid = f"P-STOCK-{compact_date}-{i:02d}"
        q = normalize(raw, review_date, pid)
        existing = load_json(proposal_path(pid), {})
        if existing:
            for key in (
                "status","approved_at","declined_at","implemented_at","deployed_at",
                "implementation","deployment","status_note"
            ):
                if key in existing:
                    q[key] = existing[key]
        save_json(proposal_path(pid), q)
        published.append(q)

    rebuild_current(review_date, published)
    return published

def set_status(proposal_id: str, status: str, note: str = ""):
    allowed = {
        "PENDING","APPROVED","DECLINED","IMPLEMENTING","TESTING",
        "READY_TO_DEPLOY","DEPLOYED","FAILED","ROLLED_BACK","SHADOW","BUNDLED"
    }
    status = status.upper()
    if status not in allowed:
        raise ValueError(f"Invalid status: {status}")
    path = proposal_path(proposal_id)
    p = load_json(path)
    if not isinstance(p, dict):
        raise FileNotFoundError(f"Unknown proposal: {proposal_id}")
    p["status"] = status
    p["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if note:
        p["status_note"] = note
    stamp = {
        "APPROVED":"approved_at","DECLINED":"declined_at","IMPLEMENTING":"implementation_started_at",
        "READY_TO_DEPLOY":"ready_to_deploy_at","DEPLOYED":"deployed_at","FAILED":"failed_at",
        "ROLLED_BACK":"rolled_back_at"
    }.get(status)
    if stamp:
        p[stamp] = p["updated_at"]
    save_json(path, p)

    same_day = []
    for f in sorted(PROPOSAL_DIR.glob("P-STOCK-*.json")):
        row = load_json(f, {})
        if row and row.get("review_date") == p.get("review_date"):
            same_day.append(row)
    rebuild_current(p.get("review_date",""), same_day)
    return p

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    pub = sub.add_parser("publish")
    pub.add_argument("--date", required=True)

    st = sub.add_parser("status")
    st.add_argument("--id", required=True)
    st.add_argument("--set", required=True)
    st.add_argument("--note", default="")

    show = sub.add_parser("show")
    show.add_argument("--id", required=True)

    args = ap.parse_args()
    if args.cmd == "publish":
        rows = publish(args.date)
        print(f"Published {len(rows)} StockTracker proposal(s).")
        for r in rows:
            print(f"  {r['proposal_id']} | {r['status']} | {r.get('title','')}")
        print(f"Review: {PROPOSAL_DIR / 'REVIEW.md'}")
    elif args.cmd == "status":
        print(json.dumps(set_status(args.id, args.set, args.note), indent=2))
    else:
        p = load_json(proposal_path(args.id))
        if not p:
            raise SystemExit(f"Unknown proposal: {args.id}")
        print(json.dumps(p, indent=2))

if __name__ == "__main__":
    main()
