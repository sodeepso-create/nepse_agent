"""Rule-based composite score with transparent reasons + news/research weight."""
from __future__ import annotations
from datetime import date

def score(indicators: dict, news_items: list | None = None, research: dict | None = None) -> dict:
    pts = 0
    reasons: list[str] = []

    trend = indicators.get("trend")
    if trend == "bullish":
        pts += 20
        reasons.append("Bullish trend (price > EMA20 > EMA50)")
    elif trend == "bearish":
        pts -= 20
        reasons.append("Bearish trend (price < EMA20 < EMA50)")

    # --- NEW: Swing Momentum / Breakout ---
    price = indicators.get("price")
    ema20 = indicators.get("ema20")
    if price and ema20:
        if price > ema20 * 1.02: # Price is 2% above EMA20
            pts += 10
            reasons.append("Short-term momentum: Price breaking above EMA20")
        elif price < ema20 * 0.98:
            pts -= 10
            reasons.append("Short-term weakness: Price dropping below EMA20")

    rsi_val = indicators.get("rsi")
    if rsi_val is not None:
        if rsi_val >= 70:
            pts -= 5 # Changed to -5 instead of -10, overbought can stay overbought
            reasons.append(f"RSI {rsi_val} suggests overbought conditions")
        elif rsi_val <= 30:
            pts += 10
            reasons.append(f"RSI {rsi_val} suggests oversold conditions")
        elif 45 <= rsi_val <= 60:
            pts += 5
            reasons.append(f"RSI {rsi_val} is in a healthy neutral range")

    macd_sig = indicators.get("macd_signal")
    if macd_sig == "bullish_crossover":
        pts += 15
        reasons.append("MACD just crossed bullish")
    elif macd_sig == "bearish_crossover":
        pts -= 15
        reasons.append("MACD just crossed bearish")

    vol_ratio = indicators.get("volume_vs_avg")
    if vol_ratio is not None:
        if vol_ratio >= 1.5:
            pts += 10
            reasons.append(f"Volume {vol_ratio}x average confirms move")

    stoch_k = indicators.get("stochastic_k")
    if stoch_k is not None:
        if stoch_k >= 80:
            pts -= 5
            reasons.append(f"Stochastic %K {stoch_k} is overbought")
        elif stoch_k <= 20:
            pts += 5
            reasons.append(f"Stochastic %K {stoch_k} is oversold")

    support = indicators.get("support")
    resistance = indicators.get("resistance")
    if price and support and resistance and resistance > support:
        position = (price - support) / (resistance - support)
        if position <= 0.15:
            pts += 8
            reasons.append("Price is near recent support")
        elif position >= 0.85:
            pts -= 8
            reasons.append("Price is near recent resistance")

    composite = max(-100, min(100, pts))
    
    # LOWERED THRESHOLD for Live Trading
    if composite >= 20:
        recommendation = "BUY"
    elif composite <= -20:
        recommendation = "SELL"
    else:
        recommendation = "HOLD"

    return {
        "as_of_date": indicators.get("as_of_date") or date.today().isoformat(),
        "composite_score": composite,
        "recommendation": recommendation,
        "reasons": reasons,
        "indicators": indicators,
    }