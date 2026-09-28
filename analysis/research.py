"""
Build research digests from collected news so analysis is "smarter"
than a single headline score.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from config import settings
from database import db
from logging_config import get_logger

logger = get_logger(__name__)


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def build_market_digest(limit_news: int = 80) -> dict:
    news = db.get_recent_news(limit=limit_news)
    if not news:
        return {
            "as_of": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "item_count": 0,
            "avg_sentiment": 0.0,
            "bullish_headlines": [],
            "bearish_headlines": [],
            "themes": [],
            "summary": "No news collected yet. Run: python main.py collect",
        }

    def weight_of(n):
        return n.get("impact_weight") or 1

    def effective_dir(n):
        d = n.get("direction")
        if d in ("bullish", "bearish"):
            return d
        s = n.get("sentiment")
        if s is None:
            return "neutral"
        if s >= 0.3:
            return "bullish"
        if s <= -0.3:
            return "bearish"
        return "neutral"

    def impact_score(n):
        sign = {"bullish": 1, "bearish": -1, "neutral": 0}[effective_dir(n)]
        return sign * weight_of(n)

    def cats(n):
        c = n.get("categories")
        if isinstance(c, str):
            try:
                return json.loads(c)
            except Exception:
                return []
        return c or []

    avg_s = _avg([n.get("sentiment") for n in news])

    bullish = sorted(
        [n for n in news if effective_dir(n) == "bullish"],
        key=impact_score, reverse=True,
    )[:8]
    bearish = sorted(
        [n for n in news if effective_dir(n) == "bearish"],
        key=impact_score,
    )[:8]

    theme_keys = {
        "dividend/bonus": ["dividend", "bonus", "right share"],
        "banking/NRB": ["bank", "nrb", "rastra"],
        "hydro/energy": ["hydro", "power", "energy", "electric"],
        "ipo/listing": ["ipo", "listing", "issue"],
        "regulation": ["sebon", "cds", "tms", "suspend", "penalty"],
        "index/turnover": ["nepse", "index", "turnover", "point"],
    }
    themes = []
    blob = " ".join((n.get("headline") or "").lower() for n in news)
    for name, kws in theme_keys.items():
        hits = sum(blob.count(k) for k in kws)
        if hits:
            themes.append({"theme": name, "mentions": hits})
    themes.sort(key=lambda x: x["mentions"], reverse=True)

    w_pos = sum(weight_of(n) for n in news if effective_dir(n) == "bullish")
    w_neg = sum(weight_of(n) for n in news if effective_dir(n) == "bearish")
    if w_pos > w_neg * 1.5:
        tone = "constructive"
    elif w_neg > w_pos * 1.5:
        tone = "cautious"
    else:
        tone = "mixed"

    summary = (
        f"Market news digest: {len(news)} items, avg sentiment {avg_s:+.2f}, tone {tone}. "
        f"Weighted bullish {w_pos} / bearish {w_neg}. "
        f"Top themes: {', '.join(t['theme'] for t in themes[:3]) or 'n/a'}."
    )

    digest = {
        "as_of": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "item_count": len(news),
        "avg_sentiment": round(avg_s, 3),
        "tone": tone,
        "bullish_headlines": [
            {
                "headline": n["headline"],
                "url": n.get("url"),
                "sentiment": n.get("sentiment"),
                "direction": n.get("direction"),
                "impact_weight": n.get("impact_weight"),
                "impact_note": n.get("impact_note"),
                "categories": cats(n),
            }
            for n in bullish
        ],
        "bearish_headlines": [
            {
                "headline": n["headline"],
                "url": n.get("url"),
                "sentiment": n.get("sentiment"),
                "direction": n.get("direction"),
                "impact_weight": n.get("impact_weight"),
                "impact_note": n.get("impact_note"),
                "categories": cats(n),
            }
            for n in bearish
        ],
        "themes": themes,
        "summary": summary,
    }
    db.save_research_digest("MARKET", digest)
    return digest


def build_symbol_digest(symbol: str, limit_news: int = 200) -> dict:
    symbol = symbol.upper()
    tagged = db.get_recent_news(symbol=symbol, limit=limit_news)
    market = db.get_recent_news(limit=limit_news)
    related = []
    seen = set()
    for n in tagged + market:
        key = n.get("url") or n.get("headline")
        if key in seen:
            continue
        text = f"{n.get('headline','')} {n.get('snippet') or ''}".upper()
        if n.get("symbol") == symbol or symbol in text:
            seen.add(key)
            related.append(n)

    avg_s = _avg([n.get("sentiment") for n in related])
    summary = (
        f"{symbol}: {len(related)} related items, avg sentiment {avg_s:+.2f}."
        if related
        else f"{symbol}: no symbol-specific news found in recent collection."
    )
    digest = {
        "as_of": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "symbol": symbol,
        "item_count": len(related),
        "avg_sentiment": round(avg_s, 3),
        "headlines": [
            {
                "headline": n["headline"],
                "url": n.get("url"),
                "sentiment": n.get("sentiment"),
                "snippet": n.get("snippet"),
            }
            for n in related[:15]
        ],
        "summary": summary,
    }
    db.save_research_digest(symbol, digest)
    return digest


def build_all_digests():
    market = build_market_digest()
    symbol_digests = {}
    symbols = {r["symbol"] for r in db.list_symbols_with_data()} | set(settings.WATCHLIST)
    for sym in sorted(symbols):
        symbol_digests[sym] = build_symbol_digest(sym)
    logger.info(
        "Research digests: market items=%d tone=%s; %d symbols",
        market["item_count"],
        market.get("tone"),
        len(symbol_digests),
    )
    return {"market": market, "symbols": symbol_digests}