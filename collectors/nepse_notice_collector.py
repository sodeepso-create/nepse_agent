"""NEPSE official company-level corporate actions via nepse-client."""
from __future__ import annotations

from collectors.base_collector import BaseCollector
from collectors.news_utils import score_headline, enrich
from config import settings
from logging_config import get_logger

logger = get_logger(__name__)


def _unwrap(item):
    while isinstance(item, list) and len(item) == 1:
        item = item[0]
    return item if isinstance(item, dict) else None


class NepseNoticeCollector(BaseCollector):
    source_name = "nepse_notices"

    def collect(self, dry_run: bool = False) -> list[dict]:
        try:
            from nepse_client import NepseClient
        except ImportError:
            logger.warning("nepse-client not installed")
            return []

        try:
            c = NepseClient()
            c.setTLSVerification(False)
            companies = c.getCompanyList() or []
        except Exception as e:
            logger.warning("NEPSE company list failed: %s", e)
            return []

        symbols = set(settings.WATCHLIST)
        id_map = {x["symbol"]: x["id"] for x in companies
                  if x.get("symbol") in symbols}

        items = []
        for sym, cid in id_map.items():
            # Dividend history
            try:
                div = _unwrap(c.getCompanyDividend(cid))
                if div:
                    cash = div.get("cashDividend")
                    bonus = div.get("bonusShare")
                    fy = div.get("fiscalYear") or ""
                    parts = []
                    if cash: parts.append(f"Cash dividend {cash}%")
                    if bonus: parts.append(f"Bonus share {bonus}%")
                    if parts:
                        headline = f"{sym} declares {', '.join(parts)} ({fy})"
                        items.append(enrich({
                            "symbol": sym,
                            "symbols": [sym],
                            "headline": headline,
                            "snippet": f"Official NEPSE dividend record for {sym}",
                            "url": f"nepse-dividend-{sym}-{fy}",
                            "published_at": None,
                            "sentiment": score_headline(headline),
                            "origin": "nepse_dividend",
                        }))
            except Exception as e:
                logger.debug("Dividend %s failed: %s", sym, e)

            # AGM
            try:
                agm = _unwrap(c.getCompanyAGM(cid))
                if agm:
                    cn = agm.get("companyNews") or {}
                    headline = (cn.get("newsHeadline") or "").strip()
                    body = (cn.get("newsBody") or "").strip()
                    if headline:
                        items.append(enrich({
                            "symbol": sym,
                            "symbols": [sym],
                            "headline": headline[:500],
                            "snippet": body[:600],
                            "url": cn.get("fullFilePath") or f"nepse-agm-{sym}",
                            "published_at": None,
                            "sentiment": score_headline(headline + " " + body),
                            "origin": "nepse_agm",
                        }))
            except Exception as e:
                logger.debug("AGM %s failed: %s", sym, e)

        logger.info("NEPSE company actions → %d items from %d companies", len(items), len(id_map))
        return items