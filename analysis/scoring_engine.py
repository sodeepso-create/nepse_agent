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
    else:
        reasons.append("Trend is sideways/unclear")

    rsi_val = indicators.get("rsi")
    if rsi_val is not None:
        if rsi_val >= 70:
            pts -= 10
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

    if indicators.get("price_vs_ema20") == "above":
        pts += 5
        reasons.append("Price above EMA20")
    else:
        pts -= 5
        reasons.append("Price below EMA20")

    vol_ratio = indicators.get("volume_vs_avg")
    if vol_ratio is not None:
        if vol_ratio >= 1.5 and trend == "bullish":
            pts += 10
            reasons.append(f"Volume {vol_ratio}x average confirms bullish move")
        elif vol_ratio >= 1.5 and trend == "bearish":
            pts -= 10
            reasons.append(f"Volume {vol_ratio}x average confirms bearish move")
        elif vol_ratio < 0.5:
            reasons.append(f"Volume is thin ({vol_ratio}x average) — low conviction")

    stoch_k = indicators.get("stochastic_k")
    if stoch_k is not None:
        if stoch_k >= 80:
            pts -= 5
            reasons.append(f"Stochastic %K {stoch_k} is overbought")
        elif stoch_k <= 20:
            pts += 5
            reasons.append(f"Stochastic %K {stoch_k} is oversold")

    atr_val = indicators.get("atr")
    price = indicators.get("price")
    if atr_val and price and price > 0:
        atr_pct = atr_val / price * 100
        if atr_pct > 4:
            reasons.append(f"Elevated volatility (ATR {atr_pct:.1f}% of price)")

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

    # --- News items (classifier-driven) ---
    if news_items:
        w_bull = 0
        w_bear = 0
        for n in news_items:
            w = n.get("impact_weight") or 1
            d = n.get("direction")
            if d == "bullish":
                w_bull += w
            elif d == "bearish":
                w_bear += w

        if w_bull or w_bear:
            net = w_bull - w_bear
            if net >= 3:
                pts += min(15, net)
                reasons.append(
                    f"News impact weighted bullish "
                    f"(w_bull={w_bull} vs w_bear={w_bear}, n={len(news_items)})"
                )
            elif net <= -3:
                pts += max(-15, net)
                reasons.append(
                    f"News impact weighted bearish "
                    f"(w_bull={w_bull} vs w_bear={w_bear}, n={len(news_items)})"
                )
            else:
                reasons.append(
                    f"{len(news_items)} news items — mixed impact "
                    f"(w_bull={w_bull} vs w_bear={w_bear})"
                )
        else:
            reasons.append(f"{len(news_items)} related news item(s) found")

    # --- Research digest (market + symbol) ---
    if research:
        sym_s = (research.get("symbol") or {}).get("avg_sentiment")
        mkt = research.get("market") or {}
        mkt_s = mkt.get("avg_sentiment")
        if sym_s is not None and research.get("symbol", {}).get("item_count", 0) > 0:
            if sym_s >= 0.25:
                pts += 7
                reasons.append(f"Symbol research digest constructive ({sym_s:+.2f})")
            elif sym_s <= -0.25:
                pts -= 7
                reasons.append(f"Symbol research digest cautious ({sym_s:+.2f})")
            else:
                reasons.append(f"Symbol research digest neutral ({sym_s:+.2f})")
        if mkt_s is not None and mkt.get("item_count", 0) > 0:
            if mkt_s >= 0.2:
                pts += 4
                reasons.append(f"Broad Nepal market news tone constructive ({mkt_s:+.2f})")
            elif mkt_s <= -0.2:
                pts -= 4
                reasons.append(f"Broad Nepal market news tone cautious ({mkt_s:+.2f})")
            themes = mkt.get("themes") or []
            if themes:
                reasons.append(
                    "Market themes: " + ", ".join(t["theme"] for t in themes[:3])
                )

    composite = max(-100, min(100, pts))
    if composite >= 30:
        recommendation = "BUY"
    elif composite <= -30:
        recommendation = "SELL"
    else:
        recommendation = "HOLD"

    return {
        "as_of_date": indicators.get("as_of_date") or date.today().isoformat(),
        "composite_score": composite,
        "recommendation": recommendation,
        "reasons": reasons,
        "indicators": indicators,
        "research_summary": (research or {}).get("symbol", {}).get("summary")
        or (research or {}).get("market", {}).get("summary"),
    }