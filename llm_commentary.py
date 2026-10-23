"""
llm_commentary.py — Optional LLM narrative generator for NEPSE reports.

Sequence:
1. Tries Groq (Cloud API) for ultra-fast generation.
2. Falls back to Ollama (Local Qwen 2.5) if Groq fails or hits a limit.

Features:
  - Fetches real-time NEPSE news via Google News RSS before generating commentary.

Usage:
  python report.py --commentary
"""
from __future__ import annotations
import os
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

# Load API keys from .env
load_dotenv()

# ---------------------------------------------------------------- News Fetching
def _fetch_news(query: str = "NEPSE stock market Nepal", limit: int = 5) -> str:
    """Fetches latest news headlines from Google News RSS."""
    print(f"\n📡 Fetching latest news for: '{query}'...")
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        
        if not items:
            return "No recent news found."
            
        news_list = []
        for item in items[:limit]:
            title = item.find("title").text
            news_list.append(f"- {title}")
            
        print(f"   ✓ Found {len(news_list)} recent headlines.")
        return "\n".join(news_list)
        
    except Exception as e:
        print(f"   ❌ Could not fetch news: {e}")
        return "News fetch failed."

# ---------------------------------------------------------------- Prompt Builder
def _build_prompt(report: dict, news: str) -> str:
    """Converts the report dictionary and news into a prompt for the LLM."""
    buys = "\n".join([f"- {t['symbol']}: {t['qty']} shares @ {t['entry_price']}" for t in report['buys']]) or "None"
    sells = "\n".join([f"- {t['symbol']}: {t['qty']} shares @ {t['exit_price']} (P/L: {t.get('pnl', 0)})" for t in report['sells']]) or "None"
    
    positions = ""
    for p in report['positions']:
        positions += f"- {p['symbol']}: {p['qty']} shares, Avg: {p['avg']:.2f}, Current: {p['current']:.2f}, Unrealized P/L: {p['unrealized']:.2f} ({p['unrealized_pct']:.2f}%)\n"
    if not positions:
        positions = "None"

    prompt = f"""You are an expert NEPSE (Nepal Stock Exchange) financial analyst.
Review the following paper trading portfolio data and the latest market news, and provide a concise, 2-paragraph commentary.

--- PORTFOLIO DATA ---
Total Equity: {report['equity']:.2f} NPR
Total Return: {report['total_return_pct']:.2f}%
Cash Available: {report['cash']:.2f} NPR
Unrealized P/L: {report['unrealized']:.2f} NPR

[Recent Buys]
{buys}

[Recent Sells]
{sells}

[Open Positions]
{positions}

--- LATEST NEPSE NEWS ---
{news}

--- YOUR TASK ---
1. Summarize the overall portfolio health and return.
2. Highlight the best and worst performing open positions.
3. Weave in relevant insights from the latest news. If a specific stock in the portfolio is mentioned in the news, explain how it affects the position. If not, comment on the general market sentiment and how it might impact the portfolio.

Keep it under 180 words. Speak directly to the trader. Frame it as paper-trading analysis, not real financial advice.
"""
    return prompt

# ---------------------------------------------------------------- LLM Callers
def _call_groq(prompt: str) -> str:
    """Call Groq API using the OpenAI client library."""
    try:
        from openai import OpenAI
    except ImportError:
        return "❌ [Error] 'openai' package not installed."

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "❌ [Error] GROQ_API_KEY environment variable not set."

    try:
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key
        )
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b", # Updated Groq model
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=400
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ [Groq Error] {e}"


def _call_ollama(prompt: str) -> str:
    """Call local Ollama instance using the official ollama python library."""
    try:
        from ollama import chat
    except ImportError:
        return "❌ [Error] 'ollama' package not installed. Run: pip install ollama"

    try:
        response = chat(
            model="qwen2.5:7b", # Matched to your local model
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        return response.message.content.strip()
    except Exception as e:
        return f"❌ [Ollama Error] {e}"

# ---------------------------------------------------------------- Main Entry
def add_commentary(report: dict) -> str:
    """Main entry point called by report.py"""
    
    # 1. Fetch News
    symbols = [p['symbol'] for p in report['positions']]
    if symbols:
        news_query = f"NEPSE {' OR '.join(symbols)}"
    else:
        news_query = "NEPSE Nepal stock market"
        
    news_text = _fetch_news(query=news_query, limit=5)
    
    # 2. Build Prompt
    prompt = _build_prompt(report, news_text)
    
    # 3. Try Groq (Cloud) First
    print("\n🤖 Generating AI Commentary using Groq (Cloud)...")
    commentary = _call_groq(prompt)
    
    # 4. Fallback to Ollama (Local) if Groq fails
    if "❌" in commentary or "Error" in commentary:
        print("⚠️ Groq failed. Falling back to Ollama (Local Qwen 2.5)...")
        commentary = _call_ollama(prompt)
        
    return f"\n{'='*62}\n 🤖 AI PORTFOLIO COMMENTARY\n{'='*62}\n{commentary}\n{'='*62}\n"