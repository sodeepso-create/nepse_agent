"""Scan news for real IPO / dividend / bonus / right share announcements.

Only sends CONFIRMED, NEPSE-relevant corporate actions.
Rejects proposals, opinions, policy stories, and foreign news.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta

from alerts.email_sender import send_email
from analysis.nepali_keywords import has_nepali
from database import db
from logging_config import get_logger

logger = get_logger(__name__)

# Each category requires: action verb + subject keyword (nearby in text)
ACTION_PATTERNS = {
    "IPO": [
        r"(sebon|securities board)\s+(approv|clear|give[s]?\s+green)",
        r"(open|opens|opening)\s+(ipo|initial public offering|issue)",
        r"(file[sd]?|filed)\s+(for|an?)\s+(ipo|issue)",
        r"(announce|announces|declar|issu)\w*\s+(ipo|fpo|initial public)",
        r"ipo\s+(open|opens|opening|approv|clear)",
        r"(issue manager|issue management)\s+(appoint|select)",
        r"(आईपीओ|प्रारम्भिक सार्वजनिक)\s+(खुल|जारी|स्वीकृत|घोषणा)",
    ],
    "Right Share": [
        r"(approv|announce|issu|open)\w*\s+right\s+share",
        r"right\s+share\s+(approv|announc|issu|open)",
        r"हकप्रद\s+(स्वीकृत|जारी|घोषणा|खुल)",
    ],
    "Bonus": [
        r"(declar|announc|approv|recommend)\w*\s+bonus",
        r"bonus\s+(share|declar|announc|approv)",
        r"बोनस\s+(सेयर\s+)?(घोषणा|स्वीकृत|जारी)",
    ],
    "Dividend": [
        r"(declar|announc|approv|recommend)\w*\s+(cash\s+)?dividend",
        r"(cash\s+)?dividend\s+(declar|announc|approv)",
        r"लाभांश\s+(घोषणा|स्वीकृत|पारित)",
    ],
    "Book Closure": [
        r"book\s+closure",
        r"किताब\s+बन्द",
    ],
    "AGM": [
        r"(annual general meeting|agm)\s+(notice|schedul|call|conven)",
        r"(notice|schedul|call)\w*\s+(annual general meeting|agm)",
        r"साधारण\s+सभा\s+(सम्बन्धी|आह्वान|सूचना)",
    ],
}

PRIORITY = ["IPO", "Right Share", "Bonus", "Dividend", "Book Closure", "AGM"]

REJECT_PHRASES = [
    "proposed", "proposes", "proposal", "may declare", "expected to",
    "likely to", "considering", "planning", "in talks", "rumour", "rumor",
    "should ", "urges", "warns", "objects", "opinion", "views",
    "प्रस्ताव", "प्रस्तावित", "योजना", "सक्ने", "हुनसक्ने",
]

FOREIGN_MARKERS = [
    "india", "indian", " bse", "sensex", "nifty", "bombay stock",
    "jio ", "reliance industries", "adani", "tata ",
    "china", "chinese", "shanghai", "hong kong",
    "japan", "nikkei", "tokyo", "nippon",
    "wall street", "nasdaq", "dow jones",
    "london", "ftse", "europe",
    "dubai", "abu dhabi", "uae",
    "singapore", "straits times",
    "colombo stock", "karachi stock", "dhaka stock",
]

NEPAL_MARKERS = [
    "nepal", "nepse", "nrb", "sebon", "nepal rastra",
    "kathmandu", "pokhara", "lalitpur", "nepali",
]


def _classify(headline: str, snippet: str) -> list[str]:
    text = f"{headline} {snippet}".lower()
    if any(neg in text for neg in REJECT_PHRASES):
        return []
    # Reject questions / analysis pieces
    if headline.strip().endswith(("?", "？")):
        return []
    hits = []
    for cat, patterns in ACTION_PATTERNS.items():
        if any(re.search(p, text) for p in patterns):
            hits.append(cat)
    return hits


def _is_nepal_relevant(headline: str, snippet: str) -> bool:
    text = f"{headline} {snippet}".lower()
    if has_nepali(headline):
        return True
    if any(w in text for w in NEPAL_MARKERS):
        return True
    if any(w in text for w in FOREIGN_MARKERS):
        return False
    return True


def _translate(text: str) -> str:
    if not has_nepali(text):
        return text
    try:
        import ollama
        from config import settings
        r = ollama.chat(
            model=settings.LLM_MODEL,
            messages=[{
                "role": "user",
                "content": (
                    "Translate this Nepali news headline to concise English. "
                    "Output only the translation, nothing else.\n\n" + text
                ),
            }],
            options={"temperature": 0.0, "num_predict": 80},
        )
        out = (r["message"]["content"] or "").strip()
        return out or text
    except Exception as e:
        logger.debug("Translate failed: %s", e)
        return text


def run_market_action_alerts(hours_back: int = 36) -> int:
    """Only scans news collected in the last N hours (default 36)."""
    cutoff = (datetime.utcnow() - timedelta(hours=hours_back)).isoformat()

    all_news = db.get_recent_news(limit=300)
    news = [n for n in all_news if (n.get("collected_at") or "") >= cutoff]

    logger.info(
        "Market actions: scanning %d of %d recent items (cutoff %s)",
        len(news), len(all_news), cutoff,
    )

    grouped = defaultdict(list)
    seen_urls = set()

    for n in news:
        headline = n.get("headline") or ""
        snippet = n.get("snippet") or ""
        if not headline:
            continue

        url = n.get("url") or headline
        if url in seen_urls:
            continue

        if not _is_nepal_relevant(headline, snippet):
            continue

        actions = _classify(headline, snippet)
        if not actions:
            continue

        key = f"market-action:{url}"
        if db.was_alert_sent(key):
            continue

        primary = next((p for p in PRIORITY if p in actions), actions[0])
        display = _translate(headline)

        grouped[primary].append({
            "headline": display,
            "original": headline if display != headline else None,
            "url": url,
            "symbol": n.get("symbol") or "market",
        })
        seen_urls.add(url)

    if not grouped:
        logger.info("Market actions: no new confirmed announcements")
        return 0

    total = sum(len(v) for v in grouped.values())

    lines = [f"NEPSE Market Actions — {total} confirmed item(s)\n"]
    for cat in PRIORITY:
        items = grouped.get(cat)
        if not items:
            continue
        lines.append(f"\n=== {cat} ({len(items)}) ===")
        for it in items:
            lines.append(f"• {it['symbol']}: {it['headline'][:150]}")
            if it["original"]:
                lines.append(f"  [original] {it['original'][:120]}")
            if it["url"]:
                lines.append(f"  {it['url']}")

    lines.append("\n— NEPSE Agent")
    body = "\n".join(lines)
    subject = f"NEPSE Market Actions ({total})"

    if send_email(subject, body):
        for items in grouped.values():
            for it in items:
                db.mark_alert_sent(f"market-action:{it['url']}")
        logger.info("Sent digest with %d items", total)
        return 1
    return 0