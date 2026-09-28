"""Shared news helpers (no collector imports — avoids circular imports)."""
from __future__ import annotations

import re

from config import settings
from analysis.nepali_keywords import has_nepali, score_sentiment_np

POSITIVE = [
    "dividend", "bonus", "profit", "growth", "gain", "surge", "record",
    "right share", "approval", "expand", "strong", "bullish", "rally",
    "upgrade", "ipo oversubscribed", "cash dividend",
]
NEGATIVE = [
    "loss", "decline", "fall", "penalty", "fraud", "suspend", "scam",
    "investigation", "weak", "bearish", "crash", "default", "warning",
    "probe", "ban", "fine", "liquidation",
]
MARKET_KEYWORDS = [
    "nepse", "share", "dividend", "bonus", "bank", "agm", "right share",
    "npr", "stock", "market", "profit", "loss", "ipo", "hydro", "insurance",
    "microfinance", "nrb", "rastra bank", "securities", "cdsc", "tms",
    "turnover", "index", "floorsheet", "mutual fund", "debenture",
]

SYMBOL_ALIASES = {
    "NABIL": ["Nabil Bank"],
    "NICA": ["NIC Asia", "NICAsia"],
    "SCB": ["Standard Chartered"],
    "EBL": ["Everest Bank"],
    "SANIMA": ["Sanima Bank"],
    "SBL": ["Siddhartha Bank"],
    "PCBL": ["Prime Commercial"],
    "CZBIL": ["Citizens Bank"],
    "PRVU": ["Prabhu Bank"],
    "NIMB": ["Nepal Investment Mega", "NIMB Bank"],
    "NBL": ["Nepal Bank"],
    "ADBL": ["Agricultural Development Bank"],
    "NMB": ["NMB Bank"],
    "SBI": ["Nepal SBI"],
    "KBL": ["Kumari Bank"],
    "MBL": ["Machhapuchchhre Bank"],
    "GBIME": ["Global IME"],
    "HBL": ["Himalayan Bank"],
    "NTC": ["Nepal Doorsanchar", "Nepal Telecom"],
    "UPPER": ["Upper Tamakoshi"],
    "HIDCL": ["Hydroelectricity Investment"],
    "NIFRA": ["Nepal Infrastructure Bank"],
    "NICL": ["Nepal Insurance"],
    "NLIC": ["Nepal Life"],
    "LICN": ["Life Insurance Corp"],
    "SICL": ["Shikhar Insurance"],
    "NRIC": ["Nepal Reinsurance"],
    "HRL": ["Himalayan Reinsurance"],
    "HDL": ["Himalayan Distillery"],
    "SHIVM": ["Shivam Cement"],
    "UNL": ["Unilever Nepal"],
    "BNT": ["Bottlers Nepal"],
    "API": ["Api Power"],
    "NHPC": ["National Hydro"],
    "CHCL": ["Chilime Hydropower"],
    "HATHY": ["Hathway"],
    "SOHL": ["Sonapur Minerals"],
    "CBBL": ["Chhimek Laghubitta"],
    "DDBL": ["Deprosc Laghubitta"],
    "RIDI": ["Ridi Power"],
    "SHPC": ["Sanima Mai Hydropower"],
    "RHPL": ["Rasuwa Gadhi"],
    "NYADI": ["Nyadi Hydropower"],
    "AHPC": ["Arun Valley Hydropower"],
    "MEN": ["Mountain Energy"],
    "TAMOR": ["Sanima Middle Tamor"],
    "BPCL": ["Butwal Power"],
    "AKJCL": ["Ankhu Khola"],
    "NGPL": ["Ngadi Group Power"],
    "MLBBL": ["Mithila Laghubitta"],
    "SANVI": ["Sanvi Energy"],
    "RSML": ["Ridi Hydropower"],
    "GBBL": ["Gurkhas Finance"],
    "SHL": ["Soaltee Hotel"],
    "OHL": ["Oriental Hotels"],
    "TRH": ["Taragaon Regency"],
    "MANDU": ["Mandu Hydropower"],
}

_ALIAS_LOOKUP = []
for _sym, _names in SYMBOL_ALIASES.items():
    for _name in _names:
        _ALIAS_LOOKUP.append((_name.lower(), _sym))
_ALIAS_LOOKUP.sort(key=lambda x: len(x[0]), reverse=True)


def score_headline(text: str) -> float:
    t = (text or "").lower()
    pos = sum(1 for w in POSITIVE if w in t)
    neg = sum(1 for w in NEGATIVE if w in t)
    if pos == 0 and neg == 0:
        if has_nepali(text):
            return score_sentiment_np(text)
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / max(pos + neg, 1)))


def tag_symbols(text: str, known_symbols: list[str] | None = None) -> list[str]:
    known = set((known_symbols or settings.WATCHLIST) + [
        "NABIL", "NICA", "HBL", "EBL", "SCB", "NMB", "GBIME", "PCBL", "SBI",
        "ADBL", "NTC", "UPPER", "HIDCL", "NIFRA", "SHL", "NHPC", "CHCL",
        "NLG", "NLIC", "LICN", "SICL", "NRIC", "UNL", "BNT", "SHIVM",
    ])
    raw = text or ""
    low = raw.lower()
    found = set()
    for sym in sorted(known, key=len, reverse=True):
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(sym)}(?![A-Za-z0-9])", raw):
            found.add(sym)
    for alias, sym in _ALIAS_LOOKUP:
        if alias in low:
            found.add(sym)
    return sorted(found)


from analysis.news_classifier import classify_news


def enrich(item: dict) -> dict:
    """Attach market-impact classification to a news dict."""
    c = classify_news(item.get("headline", ""), item.get("snippet", ""))
    item["categories"] = c["categories"]
    item["impact_weight"] = c["impact_weight"]
    item["direction"] = c["direction"]
    item["sectors"] = c["sectors"]
    item["impact_note"] = c["explanation"]
    return item