"""Real math tests for the scoring engine — verifies exact point values
against the documented rules. Catches silent logic changes before real money."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.scoring_engine import score


def _base_indicators(**overrides):
    """Baseline: neutral. Override only what each test cares about."""
    base = {
        "trend": "sideways",
        "rsi": None,
        "macd_signal": None,
        "price_vs_ema20": "below",     # -5 by default
        "volume_vs_avg": None,
        "stochastic_k": None,
        "atr": None,
        "price": None,
        "support": None,
        "resistance": None,
        "as_of_date": "2024-01-01",
    }
    base.update(overrides)
    return base


# ── Trend ────────────────────────────────────────────────────────────────

def test_bullish_trend_adds_20():
    ind = _base_indicators(trend="bullish")
    r = score(ind, news_items=None, research=None)
    # bullish +20, price below ema20 -5 = 15
    assert r["composite_score"] == 15
    assert r["recommendation"] == "HOLD"


def test_bearish_trend_subtracts_20():
    ind = _base_indicators(trend="bearish")
    r = score(ind, news_items=None, research=None)
    # -20 trend, -5 below ema20 = -25
    assert r["composite_score"] == -25


def test_sideways_trend_no_points():
    ind = _base_indicators(trend="sideways")
    r = score(ind, news_items=None, research=None)
    # 0 trend, -5 below ema20
    assert r["composite_score"] == -5


# ── RSI ──────────────────────────────────────────────────────────────────

def test_rsi_overbought_penalty():
    ind = _base_indicators(rsi=75, price_vs_ema20="above")
    r = score(ind, news_items=None, research=None)
    # rsi -10, above +5 = -5
    assert r["composite_score"] == -5


def test_rsi_oversold_bonus():
    ind = _base_indicators(rsi=25, price_vs_ema20="above")
    r = score(ind, news_items=None, research=None)
    # rsi +10, above +5 = 15
    assert r["composite_score"] == 15


def test_rsi_neutral_bonus():
    ind = _base_indicators(rsi=50, price_vs_ema20="above")
    r = score(ind, news_items=None, research=None)
    # rsi +5, above +5 = 10
    assert r["composite_score"] == 10


# ── MACD ─────────────────────────────────────────────────────────────────

def test_macd_bullish_crossover():
    ind = _base_indicators(macd_signal="bullish_crossover", price_vs_ema20="above")
    r = score(ind, news_items=None, research=None)
    # macd +15, above +5 = 20
    assert r["composite_score"] == 20


def test_macd_bearish_crossover():
    ind = _base_indicators(macd_signal="bearish_crossover")
    r = score(ind, news_items=None, research=None)
    # macd -15, below -5 = -20
    assert r["composite_score"] == -20


# ── Volume ───────────────────────────────────────────────────────────────

def test_volume_confirms_bullish():
    ind = _base_indicators(trend="bullish", volume_vs_avg=2.0)
    r = score(ind, news_items=None, research=None)
    # trend +20, vol +10, below -5 = 25
    assert r["composite_score"] == 25


def test_volume_confirms_bearish():
    ind = _base_indicators(trend="bearish", volume_vs_avg=2.0)
    r = score(ind, news_items=None, research=None)
    # trend -20, vol -10, below -5 = -35
    assert r["composite_score"] == -35
    assert r["recommendation"] == "SELL"


def test_thin_volume_no_points():
    ind = _base_indicators(volume_vs_avg=0.3)
    r = score(ind, news_items=None, research=None)
    # no vol points, below -5 = -5
    assert r["composite_score"] == -5


# ── Recommendation thresholds ───────────────────────────────────────────

def test_buy_threshold_at_30():
    # Bullish 20 + macd 15 + above 5 + rsi_oversold 10 = 50 → BUY
    ind = _base_indicators(
        trend="bullish",
        macd_signal="bullish_crossover",
        rsi=25,
        price_vs_ema20="above",
    )
    r = score(ind, news_items=None, research=None)
    assert r["composite_score"] >= 30
    assert r["recommendation"] == "BUY"


def test_sell_threshold_at_minus_30():
    ind = _base_indicators(
        trend="bearish",
        macd_signal="bearish_crossover",
        rsi=75,
    )
    r = score(ind, news_items=None, research=None)
    assert r["composite_score"] <= -30
    assert r["recommendation"] == "SELL"


def test_hold_in_middle():
    # trend +20, above +5 = 25 → HOLD
    ind = _base_indicators(trend="bullish", price_vs_ema20="above")
    r = score(ind, news_items=None, research=None)
    assert r["recommendation"] == "HOLD"


# ── Clamp ────────────────────────────────────────────────────────────────

def test_score_clamped_high():
    ind = _base_indicators(
        trend="bullish",
        macd_signal="bullish_crossover",
        rsi=25,
        price_vs_ema20="above",
        volume_vs_avg=3.0,
        stochastic_k=10,
    )
    r = score(ind, news_items=None, research=None)
    assert r["composite_score"] <= 100


def test_score_clamped_low():
    ind = _base_indicators(
        trend="bearish",
        macd_signal="bearish_crossover",
        rsi=80,
        volume_vs_avg=3.0,
        stochastic_k=90,
    )
    r = score(ind, news_items=None, research=None)
    assert r["composite_score"] >= -100


# ── News weighting ──────────────────────────────────────────────────────

def test_news_bullish_net_positive():
    ind = _base_indicators()
    news = [
        {"direction": "bullish", "impact_weight": 3},
        {"direction": "bullish", "impact_weight": 2},
    ]
    r = score(ind, news_items=news, research=None)
    # news net +5, below -5 = 0
    assert r["composite_score"] == 0


def test_news_bearish_net_negative():
    ind = _base_indicators()
    news = [
        {"direction": "bearish", "impact_weight": 4},
        {"direction": "bullish", "impact_weight": 1},
    ]
    r = score(ind, news_items=news, research=None)
    # news net -3, below -5 = -8
    assert r["composite_score"] == -8


def test_news_mixed_no_points():
    ind = _base_indicators()
    news = [
        {"direction": "bullish", "impact_weight": 1},
        {"direction": "bearish", "impact_weight": 1},
    ]
    r = score(ind, news_items=news, research=None)
    # mixed → no points, below -5 = -5
    assert r["composite_score"] == -5


# ── Research digest ─────────────────────────────────────────────────────

def test_symbol_research_constructive():
    ind = _base_indicators()
    research = {
        "symbol": {"avg_sentiment": 0.5, "item_count": 5},
        "market": {},
    }
    r = score(ind, news_items=None, research=research)
    # symbol +7, below -5 = 2
    assert r["composite_score"] == 2


def test_market_research_cautious():
    ind = _base_indicators()
    research = {
        "symbol": {},
        "market": {"avg_sentiment": -0.3, "item_count": 10, "themes": []},
    }
    r = score(ind, news_items=None, research=research)
    # market -4, below -5 = -9
    assert r["composite_score"] == -9


# ── Reasons transparency ────────────────────────────────────────────────

def test_reasons_list_not_empty():
    ind = _base_indicators(trend="bullish")
    r = score(ind, news_items=None, research=None)
    assert isinstance(r["reasons"], list)
    assert len(r["reasons"]) > 0
    assert any("Bullish" in s or "bullish" in s for s in r["reasons"])


if __name__ == "__main__":
    # Run directly: python tests\test_scoring.py
    import inspect
    fns = [f for n, f in globals().items() if n.startswith("test_") and callable(f)]
    for f in fns:
        f()
    print(f"All {len(fns)} scoring tests passed.")