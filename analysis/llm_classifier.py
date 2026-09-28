"""LLM fallback classifier using local Ollama.

Only called for headlines the rule-based classifier marked neutral/general.
Strict validation: rejects any output outside expected schema.
"""
from __future__ import annotations

import json

from logging_config import get_logger

logger = get_logger(__name__)

ALLOWED_CATEGORIES = {
    "monetary_policy", "regulation", "macro", "ipo_listing",
    "sector_banking", "sector_hydro", "sector_insurance",
    "sector_microfinance", "corporate_action", "rating_action",
    "political", "global", "index_movement", "general",
}
ALLOWED_DIRECTIONS = {"bullish", "bearish", "neutral"}
ALLOWED_SECTORS = {
    "banking", "hydropower", "insurance", "microfinance",
    "energy", "capital market", "market-wide", "single stock",
}

PROMPT_TEMPLATE = (
    "You classify NEPSE (Nepal Stock Exchange) news headlines.\n\n"
    "Headline: {headline}\n"
    "Snippet: {snippet}\n\n"
    "Return ONLY valid JSON. No markdown. No explanation outside JSON.\n\n"
    "Schema:\n"
    "{{\n"
    '  "category": one of monetary_policy, regulation, macro, ipo_listing, '
    "sector_banking, sector_hydro, sector_insurance, sector_microfinance, "
    "corporate_action, rating_action, political, global, index_movement, general\n"
    '  "direction": one of bullish, bearish, neutral\n'
    '  "weight": 1, 2, or 3\n'
    '  "sectors": list from banking, hydropower, insurance, microfinance, '
    "energy, capital market, market-wide, single stock\n"
    '  "explanation": short phrase under 100 chars\n'
    "}}\n\n"
    "Rules:\n"
    "- weight 3 = market-wide (NRB, SEBON, budget, big index move)\n"
    "- weight 2 = sector-wide\n"
    "- weight 1 = single-stock (dividend, AGM, rating)\n"
    "- direction: bullish if positive for prices, bearish if negative, neutral if factual\n"
    "- If unrelated to NEPSE/stocks, use category general, direction neutral, weight 1\n\n"
    "Examples:\n"
    'Input: "NRB cuts policy rate by 50 basis points"\n'
    'Output: {{"category":"monetary_policy","direction":"bullish","weight":3,'
    '"sectors":["banking","market-wide"],"explanation":"Rate cut boosts credit"}}\n\n'
    'Input: "Nabil Bank announces 15% cash dividend"\n'
    'Output: {{"category":"corporate_action","direction":"bullish","weight":1,'
    '"sectors":["single stock"],"explanation":"Dividend to shareholders"}}\n\n'
    'Input: "Weather forecast for Kathmandu"\n'
    'Output: {{"category":"general","direction":"neutral","weight":1,'
    '"sectors":[],"explanation":"Unrelated to market"}}\n'
)


def _validate(data: dict) -> dict | None:
    """Reject any output outside allowed values."""
    if not isinstance(data, dict):
        return None

    cat = str(data.get("category", "")).strip()
    if cat not in ALLOWED_CATEGORIES:
        logger.debug("LLM reject: bad category %r", cat)
        return None

    direction = str(data.get("direction", "")).strip().lower()
    if direction not in ALLOWED_DIRECTIONS:
        logger.debug("LLM reject: bad direction %r", direction)
        return None

    try:
        weight = int(data.get("weight", 1))
    except (ValueError, TypeError):
        weight = 1
    weight = max(1, min(3, weight))

    sectors_in = data.get("sectors") or []
    if not isinstance(sectors_in, list):
        sectors_in = []
    sectors = [s for s in sectors_in if isinstance(s, str) and s in ALLOWED_SECTORS]

    explanation = str(data.get("explanation", ""))[:150]

    return {
        "categories": [cat],
        "impact_weight": weight,
        "direction": direction,
        "sectors": sectors,
        "explanation": explanation or "LLM classified",
    }


def classify_with_llm(headline: str, snippet: str = "") -> dict | None:
    """Call Ollama. Return dict or None on failure."""
    try:
        import ollama
    except ImportError:
        logger.debug("ollama not installed")
        return None

    from config import settings

    prompt = PROMPT_TEMPLATE.format(
        headline=(headline or "")[:300],
        snippet=(snippet or "")[:300],
    )

    try:
        r = ollama.chat(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.0,
                "top_p": 0.1,
                "top_k": 10,
                "num_predict": 200,
                "repeat_penalty": 1.1,
            },
            format="json",
        )
        raw = r["message"]["content"]
        data = json.loads(raw)
        return _validate(data)
    except json.JSONDecodeError as e:
        logger.debug("LLM JSON parse failed: %s", e)
        return None
    except Exception as e:
        logger.debug("LLM classify failed: %s", e)
        return None