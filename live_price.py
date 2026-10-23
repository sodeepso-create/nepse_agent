import requests
from bs4 import BeautifulSoup

def get_live_ltp(symbol: str) -> float:
    """Fetches the real-time Last Traded Price (LTP) for a symbol."""
    symbol = symbol.upper()
    
    try:
        url = "https://merolagani.com/LatestMarket.aspx"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'class': 'table table-hover live-trading'})
        
        if table:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) > 1 and cols[0].text.strip().upper() == symbol:
                    ltp_text = cols[1].text.strip().replace(',', '')
                    return float(ltp_text)
    except Exception as e:
        print(f"Merolagani live fetch failed: {e}")

    print(f"⚠️ Could not fetch live price for {symbol}. Market might be closed.")
    return None