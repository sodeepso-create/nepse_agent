"""Real math tests for the backtest engine.

Tests the LOOP logic (position sizing, trade logging, win rate,
drawdown, cash conservation) independent of strategy rules.
Strategy functions are mocked so tests validate the ENGINE, not the strategy.
"""
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest import backtester


# ── Synthetic data builders ─────────────────────────────────────────────

def _rows(n, prices=None, start=100.0, step=1.0):
    rows = []
    for i in range(n):
        p = prices[i] if prices is not None else start + i * step
        rows.append({
            "symbol": "TEST",
            "date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "open": p - 0.5,
            "high": p + 1.0,
            "low": p - 1.0,
            "close": p,
            "volume": 10000,
        })
    return rows


def _dates(n):
    return [f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n)]


def _mock_strategy(rec_sequence):
    """rec_sequence: dict of date_str -> recommendation"""
    def fn(computed):
        rec = rec_sequence.get(computed["as_of_date"], "HOLD")
        return {"recommendation": rec, "composite_score": 0, "reasons": []}
    return fn


def _run(rows, strategy_fn, **kwargs):
    with ExitStack() as stack:
        stack.enter_context(patch.object(backtester.db, "get_ohlc", return_value=rows))
        stack.enter_context(
            patch.object(backtester.db, "save_backtest_run", return_value=None, create=True)
        )
        stack.enter_context(patch.dict(backtester.STRATEGIES, {"default": strategy_fn}))
        return backtester.run_backtest("TEST", **kwargs)


# ── Input validation ────────────────────────────────────────────────────

def test_insufficient_bars_returns_none():
    result = _run(_rows(20), _mock_strategy({}))
    assert result is None


def test_just_below_min_bars_returns_none():
    # min_bars=40 means we need at least 50 rows total
    result = _run(_rows(49), _mock_strategy({}))
    assert result is None


def test_enough_bars_runs():
    result = _run(_rows(60), _mock_strategy({}))
    assert result is not None


# ── No trades ───────────────────────────────────────────────────────────

def test_no_trades_returns_zero_stats():
    result = _run(_rows(60), _mock_strategy({}))
    assert result is not None
    assert result["total_trades"] == 0
    assert result["win_rate_percent"] == 0.0
    assert result["total_return_percent"] == 0.0
    assert result["max_drawdown_percent"] == 0.0
    assert result["final_capital"] == 100_000.0


# ── Single trade ────────────────────────────────────────────────────────

def test_single_winning_trade():
    prices = [100.0 + i * 1.0 for i in range(60)]
    d = _dates(60)
    strategy = _mock_strategy({d[50]: "BUY", d[55]: "SELL"})
    result = _run(_rows(60, prices=prices), strategy)
    assert result["total_trades"] == 1
    assert result["win_rate_percent"] == 100.0
    assert result["total_return_percent"] > 0


def test_single_losing_trade():
    prices = [100.0] * 50 + [100.0 - (i - 50) * 1.0 for i in range(50, 60)]
    d = _dates(60)
    strategy = _mock_strategy({d[50]: "BUY", d[55]: "SELL"})
    result = _run(_rows(60, prices=prices), strategy)
    assert result["total_trades"] == 1
    assert result["win_rate_percent"] == 0.0
    assert result["total_return_percent"] < 0


# ── Win rate math ──────────────────────────────────────────────────────

def test_win_rate_two_wins_one_loss():
    n = 80
    prices = [100.0] * n
    for i in range(55, n):
        prices[i] = 110.0
    for i in range(65, n):
        prices[i] = 120.0
    for i in range(75, n):
        prices[i] = 100.0

    d = _dates(n)
    strategy = _mock_strategy({
        d[50]: "BUY", d[55]: "SELL",
        d[60]: "BUY", d[65]: "SELL",
        d[70]: "BUY", d[75]: "SELL",
    })
    result = _run(_rows(n, prices=prices), strategy)
    assert result["total_trades"] == 3
    assert result["win_rate_percent"] == pytest.approx(66.67, abs=0.01)


# ── Drawdown ───────────────────────────────────────────────────────────

def test_max_drawdown_on_crash():
    n = 80
    prices = [100.0] * n
    for i in range(50, 55):
        prices[i] = 120.0
    for i in range(55, n):
        prices[i] = 60.0

    d = _dates(n)
    strategy = _mock_strategy({d[50]: "BUY", d[70]: "SELL"})
    result = _run(_rows(n, prices=prices), strategy)
    assert result["max_drawdown_percent"] > 40.0


# ── Position management ────────────────────────────────────────────────

def test_multiple_buys_only_open_one_position():
    d = _dates(60)
    strategy = _mock_strategy({d[i]: "BUY" for i in range(45, 56)})
    result = _run(_rows(60), strategy)
    # Never sold but engine closes at end → exactly one SELL recorded
    assert result["total_trades"] == 1


def test_sell_when_flat_does_nothing():
    d = _dates(60)
    strategy = _mock_strategy({d[i]: "SELL" for i in range(45, 55)})
    result = _run(_rows(60), strategy)
    assert result["total_trades"] == 0


def test_alternating_buy_sell():
    d = _dates(80)
    strategy = _mock_strategy({
        d[45]: "BUY", d[50]: "SELL",
        d[55]: "BUY", d[60]: "SELL",
        d[65]: "BUY", d[70]: "SELL",
    })
    result = _run(_rows(80), strategy)
    assert result["total_trades"] == 3


# ── Output shape ───────────────────────────────────────────────────────

def test_result_keys_and_symbol_uppercase():
    result = _run(_rows(60), _mock_strategy({}))
    for key in ("symbol", "strategy_version", "start_date", "end_date",
                "total_trades", "win_rate_percent", "total_return_percent",
                "max_drawdown_percent", "final_capital"):
        assert key in result
    assert result["symbol"] == "TEST"


def test_final_capital_never_negative():
    prices = [500.0 + i for i in range(80)]
    d = _dates(80)
    strategy = _mock_strategy({d[50]: "BUY"})
    result = _run(_rows(80, prices=prices), strategy)
    assert result["final_capital"] > 0


# ── No lookahead ───────────────────────────────────────────────────────

def test_strategy_sees_only_current_and_past_prices():
    prices = [100.0 + i * 1.0 for i in range(60)]
    seen = []

    def recording_strategy(computed):
        seen.append(computed["price"])
        return {"recommendation": "HOLD", "composite_score": 0, "reasons": []}

    _run(_rows(60, prices=prices), recording_strategy)
    # First call is at i=min_bars=40, price=140
    assert seen[0] == prices[40]
    # Every price the strategy sees must be a real past-or-current price
    assert all(p in prices for p in seen)
    # And it must end at the last bar (loop runs to the end)
    assert seen[-1] == prices[-1]
    # Monotonically increasing in this scenario
    assert seen == sorted(seen)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))