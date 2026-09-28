"""
Nepal / NEPSE / financial news collector.

Sources:
  1. Site scrapers (Merolagani, Bizmandu, Nepali Paisa, Clickmandu)
  2. ShareSansar dedicated scraper
  3. Arthasansar dedicated scraper (Nepali)
  4. NEPSE official notices (corporate actions)
  5. RSS feeds (best-effort)
  6. Google News RSS (via WebSearchCollector)
  7. Symbol tagging from headline text against known tickers
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collectors.base_collector import BaseCollector
from collectors.web_search import WebSearchCollector, DEFAULT_QUERIES
from collectors.rss_collector import RSSNewsCollector
from collectors.sharesansar_news import ShareSansarNewsCollector
from collectors.arthasansar_news import ArthasansarNewsCollector
from collectors.nepse_notice_collector import NepseNoticeCollector
from collectors.news_utils import MARKET_KEYWORDS, score_headline, tag_symbols, enrich
from config import settings
from database import db
from logging_config import get_logger

logger = get_logger(__name__)

SITE_SOURCES = {
    "merolagani": "https://merolagani.com/NewsList.aspx",
    "bizmandu": "https://bizmandu.com/",
    "nepalipaisa": "https://nepalipaisa.com/news",
    "clickmandu": "https://clickmandu.com/",
}


class NewsCollector(BaseCollector):
    source_name = "news"

    def collect_all(self, dry_run=False, include_web_search: bool = True):
        all_items = []

        for name, url in SITE_SOURCES.items():
            try:
                items = self._collect_site(name, url, dry_run=dry_run)
                all_items.extend(items)
            except Exception as e:
                logger.warning("News site '%s' failed: %s", name, e)

        try:
            rss_items = RSSNewsCollector().collect_all(dry_run=dry_run)
            all_items.extend(rss_items)
        except Exception as e:
            logger.warning("RSS news failed: %s", e)

        try:
            ss_items = ShareSansarNewsCollector().collect(dry_run=dry_run)
            all_items.extend(ss_items)
        except Exception as e:
            logger.warning("ShareSansar news failed: %s", e)

        try:
            artha_items = ArthasansarNewsCollector().collect(dry_run=dry_run)
            all_items.extend(artha_items)
        except Exception as e:
            logger.warning("Arthasansar news failed: %s", e)

        try:
            nepse_items = NepseNoticeCollector().collect(dry_run=dry_run)
            all_items.extend(nepse_items)
        except Exception as e:
            logger.warning("NEPSE notices failed: %s", e)

        if include_web_search and not dry_run:
            try:
                web_items = self._collect_web_search()
                all_items.extend(web_items)
            except Exception as e:
                logger.warning("Web search failed: %s", e)

        # Dedupe by URL
        seen = set()
        unique = []
        for it in all_items:
            u = it.get("url") or it["headline"]
            if u in seen:
                continue
            seen.add(u)
            unique.append(enrich(it))

        if unique and not dry_run:
            db.insert_news(unique, source=self.source_name)
            logger.info("Collected %d unique news/research items", len(unique))
        return unique

    def _collect_site(self, name: str, url: str, dry_run=False) -> list[dict]:
        resp = self.fetch(url)
        if dry_run:
            print(f"--- {name} ---")
            print(resp.text[:1200])
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items = []
        seen = set()
        for a in soup.select("a"):
            text = a.get_text(" ", strip=True)
            href = a.get("href") or ""
            if not text or len(text) < 25:
                continue
            low = text.lower()
            if not any(kw in low for kw in MARKET_KEYWORDS):
                continue
            full_url = href if href.startswith("http") else urljoin(url, href)
            if full_url in seen or full_url.startswith("javascript"):
                continue
            seen.add(full_url)
            symbols = tag_symbols(text)
            items.append(
                {
                    "symbol": symbols[0] if symbols else None,
                    "symbols": symbols,
                    "headline": text[:500],
                    "snippet": "",
                    "url": full_url,
                    "published_at": None,
                    "sentiment": score_headline(text),
                    "origin": name,
                }
            )
        return items[:100]

    def _collect_web_search(self) -> list[dict]:
        searcher = WebSearchCollector()
        queries = list(DEFAULT_QUERIES)
        for sym in settings.WATCHLIST[:8]:
            queries.append(f"{sym} NEPSE Nepal share news")
            queries.append(f"{sym} dividend OR bonus OR AGM Nepal")

        hits = searcher.search_many(queries, max_per_query=8)
        items = []
        for h in hits:
            title = h["title"]
            snippet = h.get("snippet") or ""
            blob = f"{title} {snippet}"
            if not any(kw in blob.lower() for kw in MARKET_KEYWORDS + ["nepal"]):
                continue
            symbols = tag_symbols(blob)
            items.append(
                {
                    "symbol": symbols[0] if symbols else None,
                    "symbols": symbols,
                    "headline": title[:500],
                    "snippet": snippet[:600],
                    "url": h["url"],
                    "published_at": None,
                    "sentiment": score_headline(blob),
                    "origin": "web_search",
                }
            )
        return items