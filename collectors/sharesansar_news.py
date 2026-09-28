"""ShareSansar news collector — parses /category/latest directly."""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collectors.base_collector import BaseCollector, CollectorError
from collectors.news_utils import score_headline, tag_symbols, enrich
from logging_config import get_logger

logger = get_logger(__name__)

SHARESANSAR_LATEST = "https://www.sharesansar.com/category/latest"


def _parse_date_from_url(url: str) -> str | None:
    """Extract YYYY-MM-DD from the end of a newsdetail URL."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", url or "")
    return m.group(1) if m else None


class ShareSansarNewsCollector(BaseCollector):
    source_name = "sharesansar_news"

    def collect(self, dry_run=False) -> list[dict]:
        try:
            resp = self.fetch(SHARESANSAR_LATEST)
        except CollectorError as e:
            logger.error("ShareSansar fetch failed: %s", e)
            return []

        if dry_run:
            print(resp.text[:2500])
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items = []
        seen = set()

        # Each news block is a div.featured-news-list
        for block in soup.select("div.featured-news-list"):
            try:
                a = block.select_one('a[href*="/newsdetail/"]')
                if not a:
                    continue
                url = urljoin(SHARESANSAR_LATEST, a.get("href", ""))
                if url in seen:
                    continue
                seen.add(url)

                # Headline: try h4 inside the link, else the link text itself
                h4 = block.find("h4")
                if h4:
                    headline = h4.get_text(" ", strip=True)
                else:
                    headline = a.get_text(" ", strip=True)

                if not headline or len(headline) < 15:
                    continue

                published = _parse_date_from_url(url)
                symbols = tag_symbols(headline)

                item = {
                    "symbol": symbols[0] if symbols else None,
                    "symbols": symbols,
                    "headline": headline[:500],
                    "snippet": "",
                    "url": url,
                    "published_at": published,
                    "sentiment": score_headline(headline),
                    "origin": "sharesansar",
                }
                items.append(enrich(item))
            except Exception as e:
                logger.debug("Skip ShareSansar block: %s", e)

        logger.info("ShareSansar → %d news items", len(items))
        return items