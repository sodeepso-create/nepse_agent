"""Shared HTTP helpers with timeouts, retries, and source-health tracking."""
import time

import requests

from config import settings
from database import db
from logging_config import get_logger

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


class CollectorError(Exception):
    pass


class BaseCollector:
    source_name = "base"

    def fetch(self, url, params=None, max_retries=3):
        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(
                    url,
                    params=params,
                    headers=HEADERS,
                    timeout=settings.REQUEST_TIMEOUT_SECONDS,
                )
                resp.raise_for_status()
                time.sleep(settings.REQUEST_DELAY_SECONDS)
                db.record_source_health(self.source_name, success=True)
                return resp
            except requests.RequestException as e:
                last_err = str(e)
                logger.warning(
                    "Fetch failed (attempt %d/%d) for %s: %s",
                    attempt,
                    max_retries,
                    url,
                    e,
                )
                time.sleep(min(2**attempt, 20))
        db.record_source_health(self.source_name, success=False, error=last_err)
        raise CollectorError(f"All {max_retries} attempts failed for {url}: {last_err}")
