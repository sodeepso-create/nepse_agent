"""
Nepal / NEPSE news via Google News RSS.

Google News RSS is an official, free, unlimited feed. No API key,
no scraping, no blocking. Replaces the old DuckDuckGo HTML scraper
which was rate-limited after ~50 queries.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import requests

from logging_config import get_logger

logger = get_logger(__name__)

GOOGLE_NEWS_URL = (
    "https://news.google.com/rss/search"
    "?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}

DEFAULT_QUERIES = [
    "NEPSE",
    "NEPSE index",
    "Nepal stock market",
    "Nepal Rastra Bank",
    "SEBON",
    "NEPSE dividend bonus",
    "Nepal IPO",
]


def _local(tag: str) -> str:
    return tag.split("}")[-1] if tag else tag


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


class WebSearchCollector:
    """Backwards-compatible name. Now backed by Google News RSS."""

    source_name = "google_news"

    def search(self, query: str, max_results: int = 12) -> list[dict]:
        """Return list of {title, url, snippet, query}."""
        url = GOOGLE_NEWS_URL.format(query=quote_plus(query))
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:
            logger.warning("Google News failed for %r: %s", query, e)
            return []

        results = []
        for item in root.findall(".//item")[:max_results]:
            try:
                title = _text(item.find("title"))
                link = _text(item.find("link"))
                pub = _text(item.find("pubDate"))
                # Google puts the publisher name inside <source>
                src_el = item.find("source")
                publisher = _text(src_el) if src_el is not None else ""
                snippet = f"{publisher}" + (f" · {pub}" if pub else "")
                if not title or not link:
                    continue
                results.append({
                    "title": title[:400],
                    "url": link,
                    "snippet": snippet[:200],
                    "query": query,
                })
            except Exception as e:
                logger.debug("Skip item: %s", e)

        logger.info("Google News %r → %d hits", query, len(results))
        return results

    def search_many(self, queries: list[str] | None = None, max_per_query: int = 10) -> list[dict]:
        queries = queries or DEFAULT_QUERIES
        seen = set()
        all_hits = []
        for q in queries:
            for hit in self.search(q, max_results=max_per_query):
                url = hit["url"]
                if url in seen:
                    continue
                seen.add(url)
                all_hits.append(hit)
        return all_hits