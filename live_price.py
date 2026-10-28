"""Merolagani quote adapter with restored scraping logic and safety metadata."""
from __future__ import annotations

from datetime import datetime, timezone
import math

import requests
from bs4 import BeautifulSoup

from quote_safety import MarketQuote, QuoteStatus

SOURCE = "merolagani.com/LatestMarket.aspx"

def get_live_quote(symbol: str) -> MarketQuote | None:
    normalized_symbol = (symbol or "").strip().upper()
    if not normalized_symbol:
        return None

    url = "https://merolagani.com/LatestMarket.aspx"
    # Restored the full Chrome User-Agent to prevent being blocked
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Restored the fallback table finder
        table = soup.find("table", {"class": "table table-hover live-trading"})
        if not table:
            for t in soup.find_all("table"):
                if "Symbol" in t.text and "LTP" in t.text:
                    table = t
                    break
                    
        if table is None:
            print(f"Merolagani quote fetch failed for {normalized_symbol}: Table not found (possibly blocked)")
            return None

        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 2 or cols[0].get_text(strip=True).upper() != normalized_symbol:
                continue
            raw_price = cols[1].get_text(strip=True).replace(",", "")
            price = float(raw_price)
            if not math.isfinite(price) or price <= 0:
                return None
                
            return MarketQuote(
                symbol=normalized_symbol,
                price=price,
                observed_at=datetime.now(timezone.utc),
                fetched_at=datetime.now(timezone.utc),
                source=SOURCE,
                status=QuoteStatus.LIVE,
            )
    except (requests.RequestException, ValueError, TypeError) as exc:
        print(f"Merolagani quote fetch failed for {normalized_symbol}: {exc}")
    return None