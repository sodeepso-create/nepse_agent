import os
from openai import OpenAI
from dotenv import load_dotenv

# 🔌 Load the API key from your .env file
load_dotenv()

def expert_trader_decision(symbol, current_price, technical_score, recent_news):
    """
    Asks the LLM to act like an expert Nepali trader.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("⚠️ GROQ_API_KEY not found in .env file!")
        return "HOLD", "Missing API Key"

    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
    
    prompt = f"""
    You are an expert NEPSE (Nepal Stock Exchange) trader with 15 years of experience. 
    You are a passive investor who trades a few times a day based on technicals and news.
    
    Analyze this stock for a potential trade RIGHT NOW:
    - Stock: {symbol}
    - Current Live Price: {current_price} NPR
    - Technical Score: {technical_score} (Anything > 30 is a technical BUY)
    - Recent News: {recent_news}
    
    Should we BUY, SELL, or HOLD?
    Respond with exactly one word: BUY, SELL, or HOLD. Then on a new line, give a 1-sentence reason.
    """
    
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b", # Updated model
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        
        answer = response.choices[0].message.content.strip()
        decision = answer.split('\n')[0].strip().upper()
        reason = answer.split('\n')[1].strip() if len(answer.split('\n')) > 1 else "LLM decision"
        
        # Clean up potential punctuation from the LLM
        decision = decision.replace('*', '').replace('.', '')
        
        return decision, reason
    except Exception as e:
        print(f"LLM Brain failed: {e}")
        return "HOLD", "Error calling LLM"