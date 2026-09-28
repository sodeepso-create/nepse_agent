"""Detect dividend / bonus / right share announcements for watchlist stocks."""
from __future__ import annotations
from alerts.prefs import get_holdings
from database import db
from logging_config import get_logger

logger = get_logger(__name__)

CA_KEYWORDS = {
    "dividend": ["dividend", "cash dividend", "लाभांश", "नगद लाभांश"],
    "bonus":    ["bonus share", "bonus", "बोनस सेयर", "बोनस"],
    "right":    ["right share", "right", "हकप्रद सेयर", "हकप्रद"],
    "book_closure": ["book closure", "किताब बन्द", "किताब बंद"],
    "agm":      ["agm", "annual general meeting", "साधारण सभा", "वार्षिक साधारण"],
}


def _action_types(text: str) -> list[str]:
    t = (text or "").lower()
    found = []
    for action, kws in CA_KEYWORDS.items():
        if any(kw.lower() in t for kw in kws):
            found.append(action)
    return found


def find_corporate_actions(days_back: int = 3) -> list[dict]:
    """Scan recent news for corporate actions on my holdings."""
    watch = set(get_holdings().keys())
    if not watch:
        return []

    news = db.get_recent_news(limit=500)
    hits = []
    for n in news:
        headline = n.get("headline") or ""
        snippet = n.get("snippet") or ""
        text = f"{headline} {snippet}"

        actions = _action_types(text)
        if not actions:
            continue

        symbols = set()
        up = text.upper()
        for sym in watch:
            if sym in up:
                symbols.add(sym)

        if not symbols:
            continue

        hits.append({
            "symbols": sorted(symbols),
            "actions": actions,
            "headline": headline,
            "url": n.get("url"),
            "date": n.get("published_at") or n.get("collected_at"),
        })
    return hits