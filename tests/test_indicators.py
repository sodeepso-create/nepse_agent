import sys
from pathlib import Path

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


if __name__ == "__main__":
    test_uptrend_detected()
    test_downtrend_detected()
    test_insufficient_data_returns_none()
    test_rsi_in_valid_range()
    test_atr_and_stochastic_present()
    print("All tests passed.")
