"""Scan ALL news for IPO / dividend / bonus / right share announcements."""
from __future__ import annotations

from collections import defaultdict

from alerts.email_sender import send_email
from database import db
from logging_config import get_logger

logger = get_logger(__name__)

KEYWORDS = {
    "IPO": ["ipo", "initial public offering", "fpo", "आईपीओ", "प्रारम्भिक सार्वजनिक"],
    "Dividend": ["dividend", "cash dividend", "लाभांश", "नगद लाभांश"],
    "Bonus": ["bonus share", "bonus", "बोनस सेयर", "बोनस"],
    "Right Share": ["right share", "हकप्रद सेयर", "हकप्रद"],
    "Book Closure": ["book closure", "किताब बन्द"],
    "AGM": ["agm", "annual general meeting", "साधारण सभा", "वार्षिक साधारण"],
}


NEGATIVE = [
    "proposed", "proposes", "proposal", "may declare", "expected to",
    "likely to", "considering", "planning", "in talks", "rumour", "rumor",
    "प्रस्ताव", "प्रस्तावित",
]


def _classify(headline: str, snippet: str) -> list[str]:
    text = f"{headline} {snippet}".lower()
    # Reject proposals / rumours — only confirmed actions
    if any(neg in text for neg in NEGATIVE):
        return []
    return [k for k, kws in KEYWORDS.items() if any(kw.lower() in text for kw in kws)]


def run_market_action_alerts() -> int:
    """Batch all new market actions into ONE email per day."""
    news = db.get_recent_news(limit=300)
    grouped = defaultdict(list)

    for n in news:
        headline = n.get("headline") or ""
        snippet = n.get("snippet") or ""
        if not headline:
            continue

        actions = _classify(headline, snippet)
        if not actions:
            continue

        url = n.get("url") or headline
        key = f"market-action:{url}"
        if db.was_alert_sent(key):
            continue

        for a in actions:
            grouped[a].append({
                "headline": headline,
                "url": url,
                "symbol": n.get("symbol") or "market",
                "date": n.get("published_at") or n.get("collected_at") or "",
            })

    if not grouped:
        return 0

    total = sum(len(v) for v in grouped.values())

    lines = [f"NEPSE Market Actions Digest — {total} new items\n"]
    for cat in ["IPO", "Dividend", "Bonus", "Right Share", "Book Closure", "AGM"]:
        items = grouped.get(cat)
        if not items:
            continue
        lines.append(f"\n=== {cat} ({len(items)}) ===")
        for it in items:
            lines.append(f"• {it['symbol']}: {it['headline'][:120]}")
            if it["url"]:
                lines.append(f"  {it['url']}")

    lines.append("\n— NEPSE Agent")
    body = "\n".join(lines)
    subject = f"NEPSE Daily Market Actions ({total} items)"

    if send_email(subject, body):
        for items in grouped.values():
            for it in items:
                db.mark_alert_sent(f"market-action:{it['url']}")
        print(f"  ✓ Sent 1 digest with {total} items")
        return 1
    return 0