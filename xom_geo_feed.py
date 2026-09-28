"""
XOM GEO/OIL FEED v1

Companion process for xom_bot_auditable_v6_1.py.
Polls Google News RSS searches for high-impact oil/geopolitical developments,
uses OpenAI to classify materiality/direction for XOM/crude, and atomically writes
geo_feed.json for the XOM bot to consume.

This process NEVER places trades. It is an information feed only.
"""
import hashlib
import html
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
GEO_FEED_PATH = Path(os.getenv("GEO_FEED_PATH", "geo_feed.json"))
GEO_STATE_PATH = Path(os.getenv("GEO_STATE_PATH", "geo_feed_state.json"))
GEO_LOG_PATH = Path(os.getenv("GEO_LOG_PATH", "geo_feed.log"))
GEO_POLL_SECONDS = int(os.getenv("GEO_POLL_SECONDS", "300"))
GEO_EVENT_MAX_AGE_HOURS = int(os.getenv("GEO_EVENT_MAX_AGE_HOURS", "24"))
GEO_MIN_MATERIALITY = float(os.getenv("GEO_MIN_MATERIALITY", "0.35"))
GEO_ALERT_MATERIALITY = float(os.getenv("GEO_ALERT_MATERIALITY", "0.65"))

QUERIES = [
    'Strait of Hormuz oil tanker shipping Iran',
    'Iran oil sanctions exports crude',
    'OPEC+ production oil meeting',
    'Saudi Arabia oil pipeline refinery tanker',
    'Middle East oil supply disruption tanker shipping',
    'Red Sea oil tanker shipping Houthi',
    'Iraq UAE Kuwait Qatar oil LNG disruption',
]

# Source names as commonly emitted by Google News RSS. Unknown sources are allowed,
# but trusted sources get a confidence boost in aggregation.
TRUSTED_SOURCES = {
    "Reuters", "Associated Press", "AP News", "Bloomberg", "CNBC",
    "Financial Times", "The Wall Street Journal", "BBC", "OPEC",
    "U.S. Energy Information Administration", "EIA"
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(GEO_LOG_PATH, encoding="utf-8")],
)
log = logging.getLogger("xom_geo_feed")
llm = OpenAI(api_key=OPENAI_API_KEY)

SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "crude_direction": {"type": "string", "enum": ["bullish", "bearish", "neutral", "mixed"]},
        "xom_direction": {"type": "string", "enum": ["bullish", "bearish", "neutral", "mixed"]},
        "materiality": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "category": {"type": "string", "enum": ["hormuz", "sanctions", "opec", "tanker_shipping", "supply", "refining", "lng", "geopolitical", "other"]},
        "supply_impact": {"type": "string", "enum": ["tighter", "looser", "unchanged", "uncertain"]},
        "summary": {"type": "string"},
        "why_xom": {"type": "string"},
    },
    "required": ["relevant", "crude_direction", "xom_direction", "materiality", "confidence", "category", "supply_impact", "summary", "why_xom"],
    "additionalProperties": False,
}


def now_utc():
    return datetime.now(timezone.utc)


def strip_html(text):
    text = html.unescape(text or "")
    return re.sub(r"<[^>]+>", " ", text).replace("  ", " ").strip()


def parse_rss_date(value):
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return now_utc()


def fetch_query(query):
    url = f"https://news.google.com/rss/search?q={quote_plus(query + ' when:1d')}&hl=en-US&gl=US&ceid=US:en"
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 XOMGeoFeed/1.0"})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    for item in root.findall(".//item"):
        title = strip_html(item.findtext("title"))
        link = item.findtext("link") or ""
        description = strip_html(item.findtext("description"))
        pub = parse_rss_date(item.findtext("pubDate") or "")
        source_el = item.find("source")
        source = strip_html(source_el.text if source_el is not None else "")
        uid = hashlib.sha256(f"{title}|{source}|{pub.isoformat()}".encode()).hexdigest()[:24]
        items.append({"id": uid, "title": title, "source": source, "url": link, "published_at": pub.isoformat(), "description": description})
    return items


def load_state():
    if not GEO_STATE_PATH.exists():
        return {"seen": {}, "events": []}
    try:
        return json.loads(GEO_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "events": []}


def atomic_json(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def classify(item):
    prompt = f"""You are a conservative market-news classifier for an XOM PAPER trading research system.
Evaluate only the supplied RSS headline/summary. Do not invent missing facts. Do not make a trade recommendation.
Focus on Iran war, Strait of Hormuz, OPEC+, sanctions/exports, tanker/shipping, crude supply, refineries/pipelines, Red Sea, Saudi/Gulf energy infrastructure, and LNG.
Materiality means potential to move crude oil prices or Exxon Mobil (XOM), not how dramatic the headline sounds.
A rumor/opinion with no confirmed operational change should receive lower materiality/confidence.

SOURCE: {item['source']}
HEADLINE: {item['title']}
SUMMARY: {item['description'][:1800]}
PUBLISHED: {item['published_at']}
"""
    resp = llm.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        text={"format": {"type": "json_schema", "name": "geo_oil_event", "schema": SCHEMA, "strict": True}},
    )
    return json.loads(resp.output_text)


def direction_value(direction):
    return {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0, "mixed": 0.0}.get(direction, 0.0)


def build_feed(events):
    cutoff = now_utc() - timedelta(hours=GEO_EVENT_MAX_AGE_HOURS)
    active = []
    for e in events:
        try:
            if datetime.fromisoformat(e["published_at"]) >= cutoff and e["analysis"]["relevant"] and e["analysis"]["materiality"] >= GEO_MIN_MATERIALITY:
                active.append(e)
        except Exception:
            pass

    weighted = 0.0
    total_weight = 0.0
    max_mat = 0.0
    for e in active:
        a = e["analysis"]
        source_factor = 1.10 if e.get("source") in TRUSTED_SOURCES else 1.0
        age_h = max(0.0, (now_utc() - datetime.fromisoformat(e["published_at"])).total_seconds() / 3600)
        recency = max(0.25, 1.0 - age_h / max(1, GEO_EVENT_MAX_AGE_HOURS))
        w = a["materiality"] * a["confidence"] * source_factor * recency
        weighted += direction_value(a["crude_direction"]) * w
        total_weight += w
        max_mat = max(max_mat, a["materiality"])
    signal = weighted / total_weight if total_weight else 0.0
    score_adjustment = max(-10.0, min(10.0, signal * 10.0))

    active.sort(key=lambda e: (e["analysis"]["materiality"] * e["analysis"]["confidence"], e["published_at"]), reverse=True)
    return {
        "generated_at": now_utc().isoformat(),
        "status": "ok",
        "signal": round(signal, 4),
        "score_adjustment": round(score_adjustment, 2),
        "max_materiality": round(max_mat, 3),
        "active_event_count": len(active),
        "events": active[:12],
    }


def run_once():
    state = load_state()
    seen = state.setdefault("seen", {})
    events = state.setdefault("events", [])
    candidates = {}
    for q in QUERIES:
        try:
            for item in fetch_query(q):
                candidates[item["id"]] = item
        except Exception as exc:
            log.warning("RSS query failed [%s]: %s", q, exc)

    new_count = 0
    for item in sorted(candidates.values(), key=lambda x: x["published_at"]):
        if item["id"] in seen:
            continue
        seen[item["id"]] = now_utc().isoformat()
        try:
            analysis = classify(item)
            if analysis["relevant"]:
                events.append({**item, "analysis": analysis, "analyzed_at": now_utc().isoformat()})
                new_count += 1
                if analysis["materiality"] >= GEO_ALERT_MATERIALITY:
                    log.warning("MATERIAL GEO EVENT | %.2f | %s | %s", analysis["materiality"], analysis["crude_direction"], item["title"])
                else:
                    log.info("geo event | %.2f | %s | %s", analysis["materiality"], analysis["crude_direction"], item["title"])
        except Exception:
            log.exception("Failed classifying: %s", item["title"])

    # Bound state size.
    seen_cutoff = now_utc() - timedelta(days=7)
    state["seen"] = {k: v for k, v in seen.items() if datetime.fromisoformat(v) >= seen_cutoff}
    event_cutoff = now_utc() - timedelta(days=3)
    state["events"] = [e for e in events if datetime.fromisoformat(e["published_at"]) >= event_cutoff]
    feed = build_feed(state["events"])
    atomic_json(GEO_STATE_PATH, state)
    atomic_json(GEO_FEED_PATH, feed)
    log.info("feed updated | new=%d active=%d signal=%+.3f adjustment=%+.2f", new_count, feed["active_event_count"], feed["signal"], feed["score_adjustment"])


def main():
    log.info("Starting XOM GEO/OIL feed | model=%s | poll=%ss | output=%s", OPENAI_MODEL, GEO_POLL_SECONDS, GEO_FEED_PATH)
    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            raise
        except Exception:
            log.exception("Geo feed cycle failed")
        time.sleep(GEO_POLL_SECONDS)


if __name__ == "__main__":
    main()
