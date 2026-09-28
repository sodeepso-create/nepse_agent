"""
Classify news by MARKET IMPACT — not just sentiment.

Catches NRB policy, SEBON regulation, macro events, sector news
that move NEPSE even without a stock ticker.

Falls back to local LLM (Ollama) for headlines the rules can't classify.
"""
from __future__ import annotations

import re

from logging_config import get_logger

logger = get_logger(__name__)

# ── Impact categories ─────────────────────────────────────────────────
# weight: 3 = market-wide, 2 = sector-wide, 1 = single-stock / low

CATEGORIES = {
    "index_movement": {
        "weight": 3,
        "sectors": ["market-wide"],
        "keywords": [
            "nepse index", "nepse gains", "nepse falls", "nepse closes",
            "market gains", "market falls", "market closes",
            "turnover of", "turnover at", "points on",
        ],
    },
    "monetary_policy": {
        "weight": 3,
        "sectors": ["banking", "market-wide"],
        "keywords": [
            "nepal rastra bank", "nrb", "monetary policy", "policy rate",
            "interest rate", "bank rate", "repo rate", "crr", "slr",
            "share holding period", "margin lending", "countercyclical",
            "counter cyclical", "refinance", "base rate",
            "deposit rate", "lending rate", "capital adequacy",
        ],
    },
    "regulation": {
        "weight": 3,
        "sectors": ["market-wide"],
        "keywords": [
            "sebon", "securities board", "securities exchange",
            "regulatory", "directive", "circular", "suspend", "suspension",
            "penalty", "insider trading", "disclosure", "compliance",
            "investigation", "probe", "ban on",
        ],
    },
    "macro": {
        "weight": 2,
        "sectors": ["market-wide"],
        "keywords": [
            "budget", "fiscal", "gdp", "inflation", "remittance",
            "forex", "foreign exchange", "trade deficit", "balance of payment",
            "capital gains tax", "economic survey", "world bank", "imf",
            "adb", "foreign aid", "loan agreement",
        ],
    },
    "ipo_listing": {
        "weight": 2,
        "sectors": ["capital market"],
        "keywords": [
            "ipo", "initial public offering", "listing", "fpo",
            "debenture", "mutual fund", "closed-end fund", "new issue",
            "oversubscribed", "primary issue",
        ],
    },
    "sector_banking": {
        "weight": 2,
        "sectors": ["banking"],
        "keywords": [
            "banking sector", "commercial bank", "development bank",
            "finance company", "npl", "non-performing loan",
            "loan growth", "deposit collection", "credit expansion",
        ],
    },
    "sector_insurance": {
        "weight": 2,
        "sectors": ["insurance"],
        "keywords": [
            "insurance authority", "life insurance", "non-life",
            "premium collection", "claim settlement", "beema samiti",
        ],
    },
    "sector_hydro": {
        "weight": 2,
        "sectors": ["hydropower", "energy"],
        "keywords": [
            "hydropower", "hydro project", "electricity authority",
            "nea", "power purchase", "ppa", "megawatt", "energy sector",
        ],
    },
    "sector_microfinance": {
        "weight": 2,
        "sectors": ["microfinance"],
        "keywords": ["microfinance", "laghubitta", "micro credit"],
    },
    "corporate_action": {
        "weight": 1,
        "sectors": ["single stock"],
        "keywords": [
            "dividend", "cash dividend", "bonus share", "right share",
            "annual general meeting", "agm", "book closure", "stock split",
            "buyback", "merger", "acquisition",
        ],
    },
    "rating_action": {
        "weight": 1,
        "sectors": ["single stock"],
        "keywords": ["rating", "upgrade", "downgrade", "credit rating"],
    },
    "political": {
        "weight": 2,
        "sectors": ["market-wide"],
        "keywords": [
            "parliament", "election", "prime minister", "budget session",
            "no-confidence", "political instability", "coalition",
        ],
    },
    "global": {
        "weight": 1,
        "sectors": ["market-wide"],
        "keywords": [
            "us fed", "federal reserve", "oil price", "crude oil",
            "china economy", "india economy", "global market",
            "us dollar", "rupee exchange",
        ],
    },
}

# ── Policy-aware direction rules ──────────────────────────────────────

DIRECTION_RULES = [
    (r"\b(opens? door|allows?|permits?|approves?)\b.{0,60}\b(intraday|short sell|short-sell|leverage)\b",
     "bullish", "New trading facility = more market activity"),
    (r"\b(upgrades?|upgraded|raises? rating|rating upgrade)\b",
     "bullish", "Rating upgrade = positive for the stock"),
    (r"\b(tax relief|tax exemption|tax cut|tax rebate|tax holiday)\b",
     "bullish", "Tax relief = more investor profit"),
    (r"\b(declares?|announces?|recommends?)\b.{0,40}\b(dividend|bonus|right share)\b",
     "bullish", "Dividend/bonus announcement = shareholder value"),
    (r"\b(nepse|market|index)\b.{0,30}\b(gains?|rises?|up|surges?|jumps?|rallies?)\b",
     "bullish", "Market up day"),
    (r"\b(nepse|market|index)\b.{0,30}\b(falls?|drops?|down|slips?|declines?|tumbles?)\b",
     "bearish", "Market down day"),
    (r"\b(cuts?|lowers?|reduces?|slashes?)\b.{0,40}\b(rate|repo|crr|slr|bank rate|policy rate)",
     "bullish", "Rate cut = cheaper credit, market-positive"),
    (r"\b(raises?|hikes?|increases?|tightens?)\b.{0,40}\b(rate|repo|crr|slr|bank rate|policy rate)",
     "bearish", "Rate hike = costlier credit, market-negative"),
    (r"\b(cuts?|reduces?|lowers?)\b.{0,40}\bshare holding period",
     "bullish", "Shorter holding period = more liquidity"),
    (r"\b(raises?|increases?|extends?)\b.{0,40}\bshare holding period",
     "bearish", "Longer holding period = less liquidity"),
    (r"\b(tightens?|curbs?|restricts?)\b.{0,40}\b(margin|loan-to-value|ltv)",
     "bearish", "Tighter margin rules = less leverage"),
    (r"\b(eases?|relaxes?|loosens?)\b.{0,40}\b(margin|loan-to-value|ltv)",
     "bullish", "Eased margin rules = more leverage"),
    (r"\b(sebon|securities board)\b.{0,50}\b(suspend|penalty|fine|ban|directive|tighten)",
     "bearish", "SEBON tightening = regulatory risk"),
    (r"\b(sebon|securities board)\b.{0,50}\b(approv|relax|ease|permit|allow)",
     "bullish", "SEBON easing = more market activity"),
]


def classify_news(headline: str, snippet: str = "") -> dict:
    """Tag a headline with impact category, weight, direction, sectors."""
    text = f"{headline} {snippet or ''}".lower()
    if not text.strip():
        return {
            "categories": [], "impact_weight": 0, "direction": "neutral",
            "sectors": [], "explanation": "empty",
        }

    matched, sectors, max_weight = [], set(), 0
    for name, cfg in CATEGORIES.items():
        if any(kw in text for kw in cfg["keywords"]):
            matched.append(name)
            max_weight = max(max_weight, cfg["weight"])
            sectors.update(cfg["sectors"])

    # Nepali fallback
    from analysis.nepali_keywords import has_nepali, tag_category_np, direction_np
    if not matched and has_nepali(text):
        np_cats = tag_category_np(text)
        for cat in np_cats:
            cfg = CATEGORIES.get(cat)
            if cfg:
                matched.append(cat)
                max_weight = max(max_weight, cfg["weight"])
                sectors.update(cfg["sectors"])

    direction, explanation = "neutral", ""
    for pattern, d, expl in DIRECTION_RULES:
        if re.search(pattern, text):
            direction, explanation = d, expl
            break

    # Nepali direction fallback
    if direction == "neutral" and has_nepali(text):
        direction = direction_np(text)
        if direction != "neutral":
            explanation = f"Nepali keyword: {direction}"

    if not explanation:
        explanation = ", ".join(matched) if matched else "general"

    result = {
        "categories": matched,
        "impact_weight": max_weight,
        "direction": direction,
        "sectors": sorted(sectors),
        "explanation": explanation,
    }

    # LLM fallback — only for headlines the rules couldn't classify
    from config import settings
    if (getattr(settings, "USE_LLM_CLASSIFIER", False)
            and not matched
            and direction == "neutral"
            and explanation == "general"
            and not has_nepali(text)):
        from analysis.llm_classifier import classify_with_llm
        llm = classify_with_llm(headline, snippet)
        if llm:
            logger.debug(
                "LLM override: %s -> %s %s w=%s",
                headline[:60], llm["direction"], llm["categories"], llm["impact_weight"],
            )
            return llm

    return result