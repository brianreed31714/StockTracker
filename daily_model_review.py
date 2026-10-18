#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env.config")
load_dotenv(ROOT / ".env", override=True)
# Explicit opt-in; defaults preserve the active v1.10 file layout.
# Set STOCKTRACKER_RUNTIME_ROOT to a folder OUTSIDE the Git checkout.
_runtime_setting = os.getenv("STOCKTRACKER_RUNTIME_ROOT", "").strip()
RUNTIME_ROOT = Path(_runtime_setting).expanduser().resolve() if _runtime_setting else ROOT
if _runtime_setting and (RUNTIME_ROOT == ROOT or ROOT in RUNTIME_ROOT.parents):
    raise ValueError("STOCKTRACKER_RUNTIME_ROOT must be outside the source repository")

DAILY_DIR = RUNTIME_ROOT / "analysis" / "daily"
PERF_DIR = RUNTIME_ROOT / "analysis" / "performance"
MARKET_TZ = ZoneInfo("America/New_York")


MODEL = os.getenv("DAILY_REVIEW_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.6-sol"))
MIN_SAMPLES = int(os.getenv("DAILY_REVIEW_MIN_PROPOSAL_SAMPLES", "12"))
PUSH_ENABLED = str(os.getenv("DAILY_REVIEW_PUSHOVER_ENABLED", "1")).strip().lower() in {"1","true","yes","on"}

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "data_quality": {"type": "string", "enum": ["GOOD","LIMITED","INSUFFICIENT"]},
        "findings": {"type": "array", "items": {"type": "string"}},
        "proposals": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "change_type": {"type": "string", "enum": ["RESEARCH","CONFIG","CODE","CODE+CONFIG"]},
                    "target": {"type": "string"},
                    "current": {"type": "string"},
                    "proposed": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "risk": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["LOW","MEDIUM","HIGH"]},
                    "recommended_mode": {"type": "string", "enum": ["SHADOW","PAPER"]},
                    "approval_required": {"type": "boolean"}
                },
                "required": ["title","change_type","target","current","proposed","evidence","risk","confidence","recommended_mode","approval_required"],
                "additionalProperties": False
            }
        }
    },
    "required": ["summary","data_quality","findings","proposals"],
    "additionalProperties": False
}

def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def deterministic_review(metrics):
    findings = []
    proposals = []
    decisions = int((metrics.get("decisions") or {}).get("rows") or 0)
    realized = metrics.get("realized") or {}
    orders = metrics.get("orders") or {}
    geo = metrics.get("geo") or {}

    if decisions == 0:
        findings.append("No decision rows were available for the review date.")
        proposals.append({
            "title": "Audit StockTracker evidence capture",
            "change_type": "RESEARCH",
            "target": "daily decision/order evidence pipeline",
            "current": "No same-day decision rows were available to the review bundle.",
            "proposed": "Verify runtime DB path, process uptime, daily CSV creation, and review-date filtering without changing trading thresholds.",
            "evidence": ["performance_input.json contains zero decision rows"],
            "risk": "The zero-row result may reflect a closed market or a valid no-data day rather than a pipeline fault.",
            "confidence": "MEDIUM",
            "recommended_mode": "SHADOW",
            "approval_required": True
        })
    else:
        findings.append(f"{decisions} decision rows and {int(orders.get('rows') or 0)} order rows were available.")
        findings.append(
            f"Realized paper P/L: ${float(realized.get('realized_pnl') or 0):+.2f} "
            f"across {int(realized.get('rows') or 0)} completed trades."
        )

    error_lines = int((geo.get("log_health") or {}).get("error_lines") or 0)
    if error_lines:
        findings.append(f"Geo-feed tail contains {error_lines} error/failed lines.")

    return {
        "summary": "Deterministic fallback review generated because the AI review was unavailable.",
        "data_quality": "LIMITED" if decisions else "INSUFFICIENT",
        "findings": findings,
        "proposals": proposals,
    }

def prompt_for(metrics):
    supporting = {
        "supporting_logs": metrics.get("supporting_logs") or {},
        "supporting_log_analysis": metrics.get("supporting_log_analysis") or {},
    }
    return f"""You are the daily model-review analyst for StockTracker, a PAPER-ONLY multi-asset momentum research system.

Your job is to study the supplied same-day evidence and propose cautious, testable improvements to the model and its instrumentation.

Hard constraints:
- The system must remain PAPER ONLY. Never propose enabling live brokerage trading.
- Do not invent evidence. If the data cannot support a conclusion, say so.
- Prefer SHADOW instrumentation when sample sizes are small or causal attribution is unclear.
- Do not tune thresholds from tiny samples. The minimum target sample before calibration is {MIN_SAMPLES}.
- Preserve portfolio caps, daily-loss controls, paper=True, and read-only dashboard behavior.
- Separate observed facts from hypotheses.
- A proposal must be actionable and narrowly scoped. Do not propose generic optimization work.
- Consider per-symbol differences, threshold hit rates, realized paper P/L, buy/sell balance, VIX effects, geo-feed contribution, SHADOW market-regime evidence, SHADOW XLF/FAS/FAZ signal and forward-outcome evidence, premarket gap/bias evidence, and evidence gaps. Treat social sentiment as unavailable unless the evidence explicitly says a source is configured.\n- Explicitly identify missed opportunities: symbols with strong observed intraday momentum/volume that produced no BUY, the maximum score reached, which gate or confirmation prevented entry when evidence permits, and what additional evidence is needed when it does not.\n- Compare opportunity capture across symbols and call out when the static score/confirmation framework appears too restrictive for high-volatility names such as NBIS, NVDA, or TSLA. Do not recommend loosening execution thresholds without forward-outcome evidence.\n- Evaluate whether fixed percentage stops/take-profit settings are mismatched to observed symbol volatility; prefer proposing SHADOW ATR/volatility-normalized research before any execution change.\n- Treat the 1% daily return objective as a stretch research benchmark, not a quota. Report evidence about return and drawdown without encouraging risk escalation.
- The supporting_log_analysis block is computed across every published row. Explicitly evaluate its integrity issues, empty tables, gate counts, and total analyzed-row coverage.\n- Distinguish requested order notional, accepted orders, fills, realized P/L, and dashboard snapshots; do not treat them as interchangeable.\n- Do not make investment recommendations to the user. Analyze the paper-trading model only.

Published supporting-log coverage and integrity (always inspect this block):
{json.dumps(supporting, indent=2)[:16000]}

Same-day sanitized evidence:
{json.dumps(metrics, indent=2)[:60000]}

Return the required JSON only."""

def ai_review(metrics):
    key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=key)
    resp = client.responses.create(
        model=MODEL,
        reasoning={"effort": os.getenv("DAILY_REVIEW_REASONING_EFFORT", "high")},
        input=prompt_for(metrics),
        text={"format": {"type": "json_schema", "name": "stocktracker_daily_review", "schema": SCHEMA, "strict": True}},
    )
    return json.loads(resp.output_text)

def performance_markdown(metrics, review):
    r = metrics.get("realized") or {}
    o = metrics.get("orders") or {}
    d = metrics.get("decisions") or {}
    supporting = metrics.get("supporting_logs") or {}
    integrity = metrics.get("supporting_log_analysis") or {}
    lines = [
        "# StockTracker Performance — Latest",
        "",
        f"Review date: **{metrics.get('review_date')}**",
        f"Generated: {metrics.get('generated_at')}",
        "",
        "## Paper-trading results",
        "",
        f"- Decisions: **{d.get('rows', 0)}**",
        f"- Orders: **{o.get('rows', 0)}** (buys {o.get('buys', 0)} / sells {o.get('sells', 0)})",
        f"- Completed paper trades: **{r.get('rows', 0)}**",
        f"- Realized paper P/L: **${float(r.get('realized_pnl') or 0):+,.2f}**",
        f"- Win/loss: **{r.get('wins', 0)}/{r.get('losses', 0)}**",
        f"- Win rate: **{r.get('win_rate_pct') if r.get('win_rate_pct') is not None else 'n/a'}%**",
        "",
        "## Review",
        "",
        review.get("summary", ""),
        "",
        f"Data quality: **{review.get('data_quality', 'UNKNOWN')}**",
        "",
        "### Supporting evidence",
        "",
        f"- Published files: **{supporting.get('published_file_count', 0)}**",
        f"- Published rows analyzed: **{supporting.get('published_row_count', 0)}**",
        f"- Integrity status: **{integrity.get('status', 'UNKNOWN')}**",
        f"- Integrity issues: **{', '.join(integrity.get('issues') or []) or 'none'}**",
        "",
        "### Findings",
    ]
    for x in review.get("findings") or []:
        lines.append(f"- {x}")
    lines += ["", "### Per-symbol paper P/L", ""]
    by = r.get("by_symbol") or {}
    if by:
        for sym, vals in by.items():
            lines.append(f"- {sym}: {vals.get('trades', 0)} completed, ${float(vals.get('pnl') or 0):+,.2f}")
    else:
        lines.append("- No completed trades for this review date.")
    lines += [
        "",
        "### Current proposal count",
        "",
        f"- {len(review.get('proposals') or [])} proposal(s) drafted for human review.",
        "",
    ]
    return "\n".join(lines)

def send_push(date_text, review):
    if not PUSH_ENABLED:
        return
    token = (os.getenv("PUSHOVER_STOCK_AGENTIC_TOKEN") or os.getenv("PUSHOVER_API_TOKEN") or "").strip()
    user = (os.getenv("PUSHOVER_STOCK_AGENTIC_GROUP_KEY") or os.getenv("PUSHOVER_USER_KEY") or "").strip()
    if not token or not user:
        return

    summary = str(review.get("summary") or "").strip()
    findings = [str(x).strip() for x in (review.get("findings") or []) if str(x).strip()]
    proposals = review.get("proposals") or []
    quality = str(review.get("data_quality") or "UNKNOWN")
    source = str(review.get("review_source") or "UNKNOWN")

    lines = [
        f"{date_text} | Data: {quality} | Review: {source}",
        summary[:420] if summary else "No summary returned.",
    ]
    if findings:
        lines.append("Key findings:")
        for item in findings[:2]:
            lines.append(f"- {item[:220]}")
    lines.append(f"Proposals: {len(proposals)}")
    if proposals:
        lines.append("ChatGPT: Review today's StockTracker proposals")

    try:
        requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": token,
                "user": user,
                "title": "StockTracker — Daily Self-Analysis",
                "message": "\n".join(lines)[:1024],
            },
            timeout=15,
        ).raise_for_status()
    except Exception:
        pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(MARKET_TZ).date().isoformat())
    args = ap.parse_args()

    bundle = DAILY_DIR / args.date / "performance_input.json"
    metrics = read_json(bundle)
    if not isinstance(metrics, dict):
        raise SystemExit(f"Missing review bundle: {bundle}")

    try:
        review = ai_review(metrics)
        review["review_source"] = "OPENAI"
        review["model"] = MODEL
    except Exception as exc:
        # Auth/configuration errors are operational failures, not successful reviews.
        # Avoid logging exception text: provider errors can contain parts of API keys.
        status = getattr(exc, "status_code", None)
        if status in (401, 403) or type(exc).__name__ in {"AuthenticationError", "PermissionDeniedError"}:
            print(f"AI review FAILED: authentication/permission error (HTTP {status or 'unknown'}).")
            print("Review and proposals not published. Update OPENAI_API_KEY, then rerun.")
            raise SystemExit(2)
        print(f"AI review warning: {type(exc).__name__} (details redacted)")
        review = deterministic_review(metrics)
        review["review_source"] = "DETERMINISTIC_FALLBACK"
        review["model"] = None

    review["review_date"] = args.date
    review["generated_at"] = datetime.now(MARKET_TZ).isoformat()

    out_dir = DAILY_DIR / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "daily_model_review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")

    md = [
        "# StockTracker Daily Model Review",
        "",
        f"Date: **{args.date}**",
        "",
        review.get("summary", ""),
        "",
        "## Findings",
        "",
    ]
    for x in review.get("findings") or []:
        md.append(f"- {x}")
    md += ["", "## Draft proposals", ""]
    if review.get("proposals"):
        for i, p in enumerate(review["proposals"], 1):
            md += [
                f"### {i}. {p.get('title', 'Untitled')}",
                "",
                f"- Type: {p.get('change_type')}",
                f"- Target: {p.get('target')}",
                f"- Current: {p.get('current')}",
                f"- Proposed: {p.get('proposed')}",
                f"- Confidence: {p.get('confidence')}",
                f"- Mode: {p.get('recommended_mode')}",
                f"- Risk: {p.get('risk')}",
                "",
            ]
    else:
        md.append("No proposals drafted.")
    (out_dir / "daily_model_review.md").write_text("\n".join(md), encoding="utf-8")

    PERF_DIR.mkdir(parents=True, exist_ok=True)
    perf = {"metrics": metrics, "review": review}
    (PERF_DIR / "latest.json").write_text(json.dumps(perf, indent=2), encoding="utf-8")
    (PERF_DIR / "latest.md").write_text(performance_markdown(metrics, review), encoding="utf-8")

    send_push(args.date, review)
    print(f"StockTracker daily review complete: {len(review.get('proposals') or [])} proposal(s)")

if __name__ == "__main__":
    main()
