"""Read-only ZPTA headline sentiment join; no model fitting or broker actions.

Input headline CSV columns: published_at_iso (timezone-aware), headline,
url, source, scope (zpta|sector), sentiment (positive|neutral|negative).
Timestamp is first-publication time, not article retrieval time.
"""
import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
VALID_SCOPES = {"zpta", "sector"}
VALID_SENTIMENTS = {"positive", "neutral", "negative"}


def load_news(path):
    items, seen = [], set()
    with Path(path).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dt = datetime.fromisoformat(row["published_at_iso"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError("News timestamp must include timezone")
            scope, sentiment = row["scope"].strip().lower(), row["sentiment"].strip().lower()
            if scope not in VALID_SCOPES or sentiment not in VALID_SENTIMENTS:
                raise ValueError("Unknown scope or sentiment")
            if not row["url"].strip() or not row["headline"].strip():
                raise ValueError("Headline and source URL required")
            key = row["url"].strip().lower().split("?")[0]
            if key in seen:
                continue
            seen.add(key)
            items.append({"published": dt.astimezone(NY), "scope": scope,
                          "sentiment": sentiment, "url": row["url"].strip()})
    return sorted(items, key=lambda x: x["published"])


def join(price_rows, news, lookback_days=3):
    result = []
    for row in price_rows:
        signal_day = datetime.fromisoformat(row["date"]).date()
        cutoff = datetime.combine(signal_day, time(16, 0), NY)
        window_start = cutoff - timedelta(days=lookback_days)
        visible = [n for n in news if window_start < n["published"] <= cutoff]
        out = dict(row)
        for scope in ("zpta", "sector"):
            group = [n for n in visible if n["scope"] == scope]
            out[scope + "_positive_count"] = sum(n["sentiment"] == "positive" for n in group)
            out[scope + "_negative_count"] = sum(n["sentiment"] == "negative" for n in group)
            out[scope + "_neutral_count"] = sum(n["sentiment"] == "neutral" for n in group)
            out[scope + "_sentiment_score"] = out[scope + "_positive_count"] - out[scope + "_negative_count"]
        out["news_urls"] = ";".join(n["url"] for n in visible)
        result.append(out)
    return result


def summarize(rows):
    from analysis.zpta_down_streak_noon_study import stats
    cohorts = defaultdict(list)
    for row in rows:
        if row["down_streak"] not in (2, 3):
            continue
        for scope in ("zpta", "sector"):
            score = row[scope + "_sentiment_score"]
            label = "positive" if score > 0 else "negative" if score < 0 else "neutral_or_none"
            cohorts[f"down_{row['down_streak']}_{scope}_{label}"].append(row)
    return {k: {"next_noon": stats(v, "next_noon_vs_signal_close_pct"),
                "next_eod": stats(v, "next_eod_vs_signal_close_pct")}
            for k, v in sorted(cohorts.items())}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prices", type=Path, required=True)
    p.add_argument("--headlines", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    with a.prices.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["down_streak"] = int(r["down_streak"])
        for col in ("next_noon_vs_signal_close_pct", "next_eod_vs_signal_close_pct"):
            r[col] = float(r[col]) if r[col] else None
    joined = join(rows, load_news(a.headlines))
    a.out.mkdir(parents=True, exist_ok=True)
    with (a.out / "price_news_join.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(joined[0]) if joined else [])
        if joined:
            writer.writeheader()
            writer.writerows(joined)
    report = {"source": "headline CSV with individually cited original URLs",
              "rows": len(joined), "cohorts": summarize(joined),
              "limitations": ["Exploratory association only; not causation or trading evidence",
                              "Missing headlines are not evidence of news-free days",
                              "Zero score mixes neutral and no-news exposures",
                              "Requires chronological holdout, confidence intervals, matched baselines and headline coverage audit"]}
    (a.out / "sentiment_summary.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
