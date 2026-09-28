"""RSS-based Nepal / business news — more reliable than brittle HTML scrapers."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from collectors.base_collector import BaseCollector
from collectors.news_utils import MARKET_KEYWORDS, score_headline, tag_symbols
from logging_config import get_logger

logger = get_logger(__name__)

RSS_FEEDS = {
    "onlinekhabar_en": "https://english.onlinekhabar.com/feed",
    "kathmandu_post": "https://kathmandupost.com/rss",
    "bizmandu": "https://bizmandu.com/feed",
}


def _local(tag: str) -> str:
    return tag.split("}")[-1] if tag else tag


def _text(el) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


class RSSNewsCollector(BaseCollector):
    source_name = "rss"

    def collect_all(self, dry_run=False) -> list[dict]:
        items = []
        for name, url in RSS_FEEDS.items():
            try:
                items.extend(self._parse_feed(name, url, dry_run=dry_run))
            except Exception as e:
                logger.warning("RSS feed '%s' failed: %s", name, e)
        return items

    def _parse_feed(self, name: str, url: str, dry_run=False) -> list[dict]:
        resp = self.fetch(url)
        if dry_run:
            print(f"--- rss:{name} ---")
            print(resp.text[:1000])
            return []

        root = ET.fromstring(resp.content)
        items = []
        for node in root.iter():
            if _local(node.tag) != "item":
                continue
            title = desc = link = pub = ""
            for child in list(node):
                ln = _local(child.tag)
                if ln == "title":
                    title = _text(child)
                elif ln in ("description", "summary"):
                    desc = re.sub(r"<[^>]+>", " ", _text(child))
                    desc = re.sub(r"\s+", " ", desc).strip()
                elif ln == "link":
                    link = _text(child) or (child.get("href") or "")
                elif ln == "pubDate":
                    pub = _text(child)
            if not title or len(title) < 20:
                continue
            blob = f"{title} {desc}".lower()
            # Keep finance / Nepal market-related items; also keep general Nepal econ
            strong = (
                "nepse", "share market", "stock market", "dividend", "bonus share",
                "right share", "ipo", "floorsheet", "securities board", "sebon",
                "listed compan", "turnover", "banking sector", "nrb ", "rastra bank",
                "mutual fund", "debenture", "agm", "cdsc", "microfinance",
            )
            finance_hit = any(kw in blob for kw in strong) or (
                any(kw in blob for kw in ("bank", "insurance", "hydro"))
                and any(kw in blob for kw in ("profit", "loss", "share", "dividend", "ipo", "nepse", "nrb"))
            )
            if not finance_hit:
                continue
            symbols = tag_symbols(f"{title} {desc}")
            items.append(
                {
                    "symbol": symbols[0] if symbols else None,
                    "symbols": symbols,
                    "headline": title[:500],
                    "snippet": desc[:600],
                    "url": link or url,
                    "published_at": pub or None,
                    "sentiment": score_headline(f"{title} {desc}"),
                    "origin": f"rss:{name}",
                }
            )
        logger.info("RSS %s → %d finance-related items", name, len(items))
        return items
