import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis import indicators as ind


def _fake_rows(n=60, start_price=100.0, trend=0.5):
    rows = []
    price = start_price
    for i in range(n):
        price += trend
        # valid calendar-ish dates
        day = (i % 28) + 1
        month = (i // 28) % 12 + 1
        year = 2024 + (i // 28) // 12
        rows.append(
            {
                "symbol": "TEST",
                "date": f"{year:04d}-{month:02d}-{day:02d}",
                "open": price - 0.5,
                "high": price + 1,
                "low": price - 1,
                "close": price,
                "volume": 10000 + (i * 10),
            }
        )
    return rows


def test_uptrend_detected():
    rows = _fake_rows(60, trend=1.0)
    computed = ind.compute_all(rows)
    assert computed is not None
    assert computed["trend"] == "bullish"


def test_downtrend_detected():
    rows = _fake_rows(60, trend=-1.0)
    computed = ind.compute_all(rows)
    assert computed is not None
    assert computed["trend"] == "bearish"


def test_insufficient_data_returns_none():
    rows = _fake_rows(5)
    assert ind.compute_all(rows) is None


def test_rsi_in_valid_range():
    rows = _fake_rows(60, trend=0.8)
    df = ind.to_dataframe(rows)
    rsi_series = ind.rsi(df)
    valid = rsi_series.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_atr_and_stochastic_present():
    rows = _fake_rows(60, trend=0.3)
    computed = ind.compute_all(rows)
    assert computed["atr"] is not None
    assert computed["stochastic_k"] is not None


def test_rsi_matches_wilder_textbook():
    """RSI must match Wilder's classic textbook values within tolerance."""
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
              45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00,
              46.03, 46.41, 46.22, 45.64]
    rows = [
        {
            "symbol": "TEST",
            "date": f"2024-01-{i+1:02d}",
            "open": c, "high": c + 0.5, "low": c - 0.5,
            "close": c, "volume": 1000,
        }
        for i, c in enumerate(closes)
    ]
    df = ind.to_dataframe(rows)
    rsi_series = ind.rsi(df)
    val = rsi_series.iloc[14]
    assert val == pytest.approx(70.53, abs=0.5), f"RSI got {val}, expected ~70.53"


if __name__ == "__main__":
    test_uptrend_detected()
    test_downtrend_detected()
    test_insufficient_data_returns_none()
    test_rsi_in_valid_range()
    test_atr_and_stochastic_present()
    test_rsi_matches_wilder_textbook()
    print("All tests passed.")