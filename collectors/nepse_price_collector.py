"""
NEPSE price collectors.

History source:  nepseman-api (official NEPSE, ~1 year) with Merolagani fallback.
Live snapshot:   ShareSansar live trading table.
"""
from datetime import datetime
from urllib.parse import quote

from bs4 import BeautifulSoup

from collectors.base_collector import BaseCollector, CollectorError
from config import settings
from database import db
from logging_config import get_logger

logger = get_logger(__name__)

MEROLAGANI_GRAPH = (
    "https://merolagani.com/handlers/webrequesthandler.ashx"
    "?type=get_company_graph&symbol={symbol}&range={range_}"
)
SHARESANSAR_LIVE = "https://www.sharesansar.com/live-trading"
MEROLAGANI_DETAIL = "https://merolagani.com/CompanyDetail.aspx?symbol={symbol}"


def _parse_us_date(s: str) -> str:
    """Convert MM/DD/YYYY to ISO YYYY-MM-DD."""
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s


def _to_float(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").replace("Rs.", "").replace("%", "").strip()
    if not s or s == "-":
        return None
    return float(s)


def _to_int(val):
    f = _to_float(val)
    return int(f) if f is not None else None


class NepsePriceCollector(BaseCollector):
    source_name = "nepse_price"

    def collect_today_prices(self, dry_run=False, symbol=None):
        """
        Collect live LTP snapshot from ShareSansar.
        If symbol is set, only keep that ticker.
        """
        resp = self.fetch(SHARESANSAR_LIVE)
        if dry_run:
            print(resp.text[:2500])
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.select_one("table.table") or soup.select_one("table")
        if table is None:
            raise CollectorError("ShareSansar live table not found — page markup may have changed")

        headers = [
            th.get_text(strip=True).lower()
            for th in table.select("thead th, tr th")
        ]
        rows = []
        for tr in table.select("tbody tr"):
            cells = [td.get_text(strip=True) for td in tr.select("td")]
            if len(cells) < 8:
                continue
            try:
                sym = cells[1].upper()
                if symbol and sym != symbol.upper():
                    continue

                def col(name, fallback_idx):
                    if name in headers:
                        return cells[headers.index(name)]
                    return cells[fallback_idx] if fallback_idx < len(cells) else None

                open_p = _to_float(col("open", 5))
                high = _to_float(col("high", 6))
                low = _to_float(col("low", 7))
                close = _to_float(col("ltp", 2))
                volume = _to_int(col("volume", 9) if len(cells) > 9 else cells[-1])
                if close is None:
                    continue
                rows.append({
                    "symbol": sym,
                    "date": datetime.now().date().isoformat(),
                    "open": open_p or close,
                    "high": high or close,
                    "low": low or close,
                    "close": close,
                    "volume": volume or 0,
                })
                db.upsert_security(sym)
            except (ValueError, IndexError) as e:
                logger.debug("Skip row %s: %s", cells[:4], e)

        if rows:
            db.insert_ohlc_rows(rows, source="sharesansar")
            logger.info("Collected %d live price rows from ShareSansar", len(rows))
        else:
            logger.warning("0 live rows parsed from ShareSansar")
        return rows

    def collect_history(self, symbol, range_="12m", dry_run=False):
        """
        Fetch historical OHLC via nepseman-api (official NEPSE).
        Returns ~1 year (~230 rows). Falls back to Merolagani on failure.
        """
        symbol = symbol.upper()
        try:
            import asyncio
            from nepseman_api import NepseClient

            async def _fetch():
                async with NepseClient() as nepse:
                    return await nepse.price_history(symbol)

            data = asyncio.run(_fetch())
            if not data:
                raise CollectorError("nepseman returned no data")

            rows = []
            for q in data:
                try:
                    d = str(q.get("businessDate") or "").strip()
                    if not d:
                        continue
                    rows.append({
                        "symbol": symbol,
                        "date": d,
                        "open": None,
                        "high": _to_float(q.get("highPrice")),
                        "low": _to_float(q.get("lowPrice")),
                        "close": _to_float(q.get("closePrice")),
                        "volume": _to_float(q.get("totalTradedQuantity")) or 0,
                    })
                except Exception as e:
                    logger.debug("Skip quote %s: %s", q, e)

            if dry_run:
                print(f"[nepseman] {symbol}: {len(rows)} rows (dry-run)")
                print(rows[:3])
                return []

            if rows:
                db.upsert_security(symbol)
                db.insert_ohlc_rows(rows, source="nepseman")
                logger.info(
                    "Collected %d history rows for %s from nepseman-api",
                    len(rows), symbol,
                )
            return rows

        except Exception as e:
            logger.warning(
                "nepseman-api failed for %s: %s — falling back to Merolagani",
                symbol, e,
            )
            return self._collect_history_merolagani(symbol, range_=range_, dry_run=dry_run)

    def _collect_history_merolagani(self, symbol, range_="12m", dry_run=False):
        """Fallback: fetch historical OHLC from Merolagani graph API (63 rows)."""
        symbol = symbol.upper()
        url = MEROLAGANI_GRAPH.format(symbol=quote(symbol), range_=range_)
        resp = self.fetch(url)
        if dry_run:
            print(resp.text[:2000])
            return []

        try:
            data = resp.json()
        except Exception as e:
            raise CollectorError(f"Merolagani graph response not JSON: {e}") from e

        if data.get("msgType") not in (None, "ok") and "quotes" not in data:
            raise CollectorError(f"Unexpected Merolagani payload: {str(data)[:200]}")

        quotes = data.get("quotes") or []
        rows = []
        for q in quotes:
            try:
                d = _parse_us_date(str(q.get("date", "")))
                rows.append({
                    "symbol": symbol,
                    "date": d,
                    "open": _to_float(q.get("open")),
                    "high": _to_float(q.get("high")),
                    "low": _to_float(q.get("low")),
                    "close": _to_float(q.get("close")),
                    "volume": _to_float(q.get("volume")) or 0,
                })
            except Exception as e:
                logger.debug("Skip quote %s: %s", q, e)

        if rows:
            db.upsert_security(symbol, company_name=data.get("name"))
            db.insert_ohlc_rows(rows, source="merolagani")
            logger.info("Collected %d history rows for %s from Merolagani", len(rows), symbol)
        else:
            logger.warning("0 history rows for %s", symbol)
        return rows

    def collect_watchlist_history(self, symbols=None, range_="12m", dry_run=False):
        symbols = symbols or settings.WATCHLIST
        all_rows = []
        for sym in symbols:
            try:
                rows = self.collect_history(sym, range_=range_, dry_run=dry_run)
                all_rows.extend(rows)
            except Exception as e:
                logger.error("History collect failed for %s: %s", sym, e)
        return all_rows

    def collect_live_quote(self, symbol):
        """Single-symbol LTP from Merolagani company page."""
        symbol = symbol.upper()
        url = MEROLAGANI_DETAIL.format(symbol=quote(symbol))
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")
        price_el = soup.select_one(
            "#ctl00_ContentPlaceHolder1_CompanyDetail1_lblMarketPrice"
        )
        if not price_el:
            raise CollectorError(f"Could not find market price for {symbol}")
        price = _to_float(price_el.get_text())
        return {"symbol": symbol, "ltp": price, "date": datetime.now().date().isoformat()}