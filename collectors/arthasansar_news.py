"""Arthasansar news collector (Nepali)."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collectors.base_collector import BaseCollector, CollectorError
from collectors.news_utils import score_headline, tag_symbols, enrich
from logging_config import get_logger

logger = get_logger(__name__)

BASE = "https://arthasansar.com"
CATEGORIES = [
    "/category/share-market/",
    "/category/banking/",
    "/category/economy/",
]


class ArthasansarNewsCollector(BaseCollector):
    source_name = "arthasansar"

    def collect(self, dry_run=False) -> list[dict]:
        items = []
        seen = set()
        for path in CATEGORIES:
            try:
                url = urljoin(BASE, path)
                resp = self.fetch(url)
                if dry_run:
                    print(resp.text[:1500])
                    continue
                soup = BeautifulSoup(resp.text, "lxml")
                for li in soup.select("ul.category__news--list > li"):
                    h3 = li.find("h3", class_="title")
                    if not h3:
                        continue
                    a = h3.find("a")
                    if not a:
                        continue
                    headline = a.get_text(" ", strip=True)
                    href = a.get("href") or ""
                    full_url = href if href.startswith("http") else urljoin(BASE, href)
                    if not headline or full_url in seen:
                        continue
                    seen.add(full_url)
                    p = li.find("p")
                    snippet = p.get_text(" ", strip=True) if p else ""
                    symbols = tag_symbols(f"{headline} {snippet}")
                    item = {
                        "symbol": symbols[0] if symbols else None,
                        "symbols": symbols,
                        "headline": headline[:500],
                        "snippet": snippet[:600],
                        "url": full_url,
                        "published_at": None,
                        "sentiment": score_headline(f"{headline} {snippet}"),
                        "origin": "arthasansar",
                    }
                    items.append(enrich(item))
            except Exception as e:
                logger.warning("Arthasansar %s failed: %s", path, e)
        logger.info("Arthasansar → %d news items", len(items))
        return items