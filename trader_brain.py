import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
def expert_trader_decision(symbol, current_price, technical_score, recent_news):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key: 
        return "HOLD", "Missing API Key"

    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
    
    prompt = f"""
    You are a highly disciplined, conservative expert NEPSE trader managing a real portfolio.
    Analyze this stock carefully before making a decision:
    - Stock: {symbol}
    - Current Live Price: {current_price} NPR
    - Technical Score: {technical_score} (Scores > 35 are strong BUY signals; < -20 are strong SELL signals)
    - Recent News: {recent_news}
    
    Strict Trading Rules:
    1. DO NOT overtrade. We only want 1 or 2 high-probability trades per day.
    2. Only say BUY if the technical score is strong (> 35) AND there is no negative news.
    3. Only say SELL if the technical trend is definitively broken (score < -20) OR there is highly damaging news.
    4. If the score is neutral (between -20 and 35), you MUST say HOLD.
    5. When in doubt, protect capital and say HOLD.
    
    Should we BUY, SELL, or HOLD? 
    Respond with exactly one word (BUY, SELL, or HOLD), then a 1-sentence reason on a new line.
    """
    
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1  # Lowered from 0.2 to make the AI more deterministic/consistent
        )
        answer = response.choices[0].message.content.strip()
        
        # Safely parse the response
        lines = answer.split('\n')
        decision = lines[0].strip().upper().replace('*', '').replace('.', '').replace('"', '').replace("'", "")
        
        # If the LLM gets chatty and adds extra text on the first line (e.g., "Decision: BUY")
        if "BUY" in decision: decision = "BUY"
        elif "SELL" in decision: decision = "SELL"
        elif "HOLD" in decision: decision = "HOLD"
        else: decision = "HOLD" # Fallback if it outputs something weird

        reason = lines[1].strip() if len(lines) > 1 else "LLM decision (no reason provided)"
        
        return decision, reason
        
    except Exception as e:
        return "HOLD", f"API Error: {e}"