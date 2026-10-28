import os
from datetime import datetime
from dataclasses import dataclass

@dataclass
class Quote:
    symbol: str
    price: float
    fetch_time: datetime
    source: str
    status: str  # "FRESH", "MISSING", "STALE"

def get_live_quote(symbol: str) -> Quote:
    symbol = symbol.upper()
    now = datetime.now()

    # 1. Primary: Use nepsepy's today_price() endpoint
    try:
        from nepsepy import NepseClient
        with NepseClient() as client:
            prices_response = client.today_price(page=1, size=500)
            stocks = prices_response.get("content", [])
            
            for stock in stocks:
                if stock.get("symbol") == symbol:
                    # Priority list based on actual nepsepy payload
                    for key in ["lastTradedPrice", "averageTradedPrice", "closePrice", "previousClosingPrice"]:
                        val = stock.get(key)
                        if val is not None:
                            try:
                                price = float(val)
                                if price > 0:
                                    return Quote(symbol, price, now, "NEPSE API (nepsepy)", "FRESH")
                            except (ValueError, TypeError):
                                pass
                    break  # Symbol found, but no valid price keys matched
                    
    except Exception as e:
        # Optional: print(f"nepsepy error: {e}") to debug if needed
        pass

    # 2. Fallback: Scrape Merolagani
    try:
        import requests
        from bs4 import BeautifulSoup
        url = "https://merolagani.com/LatestMarket.aspx"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        table = soup.find('table', {'class': 'table table-hover live-trading'})
        if not table:
            for t in soup.find_all('table'):
                if "Symbol" in t.text and "LTP" in t.text:
                    table = t
                    break

        if table:
            for row in table.find_all('tr'):
                cols = row.find_all('td')
                if len(cols) > 1 and cols[0].text.strip().upper() == symbol:
                    ltp_text = cols[1].text.strip().replace(',', '')
                    if ltp_text:
                        price = float(ltp_text)
                        if price > 0:
                            return Quote(symbol, price, now, "Merolagani", "FRESH")
    except Exception:
        pass

    return Quote(symbol, 0.0, now, "Unknown", "MISSING")


def get_live_ltp(symbol: str) -> float | None:
    quote = get_live_quote(symbol)
    if quote.status == "FRESH":
        return quote.price
    return None