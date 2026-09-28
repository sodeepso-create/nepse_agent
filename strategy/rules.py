"""Strategy variants that share the same output shape as scoring_engine.score()."""
from analysis.scoring_engine import score as default_score


def default_strategy(indicators, news_items=None):
    return default_score(indicators, news_items=news_items)


def conservative_strategy(indicators, news_items=None):
    """Only BUY on strong trend + volume confirmation + RSI not overbought."""
    result = default_score(indicators, news_items=news_items)
    reasons = list(result["reasons"])
    rec = result["recommendation"]
    pts = result["composite_score"]

    if rec == "BUY":
        ok = (
            indicators.get("trend") == "bullish"
            and (indicators.get("volume_vs_avg") or 0) >= 1.2
            and (indicators.get("rsi") or 50) < 68
        )
        if not ok:
            rec = "HOLD"
            pts = min(pts, 25)
            reasons.append("Conservative filter: BUY blocked (needs trend+volume+RSI<68)")

    if rec == "SELL" and indicators.get("trend") != "bearish":
        rec = "HOLD"
        pts = max(pts, -25)
        reasons.append("Conservative filter: SELL blocked without bearish trend")

    return {
        "as_of_date": result["as_of_date"],
        "composite_score": pts,
        "recommendation": rec,
        "reasons": reasons,
        "indicators": indicators,
    }


STRATEGIES = {
    "default": default_strategy,
    "conservative": conservative_strategy,
}
