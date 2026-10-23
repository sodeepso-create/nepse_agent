"""Walk-forward test for backtest v3 — same config, three time windows.

Splits history into three separate windows so we can see whether the
edge survives out-of-sample, or was curve-fit to the full 14 years.
"""
from __future__ import annotations

from unittest.mock import patch

from alerts.prefs import get_watchlist
from backtest import backtester_v3
from database import db

WINDOWS = [
    ("2012-01-01", "2019-12-31", "W1 (2012-2019)"),
    ("2020-01-01", "2023-12-31", "W2 (2020-2023)"),
    ("2024-01-01", "2026-12-31", "W3 (2024-2026)"),
]


def _filter(all_rows, start, end):
    return [r for r in all_rows if start <= r["date"] <= end]


def run_window(symbol, start, end):
    all_rows = db.get_ohlc(symbol, limit_days=100000)
    filtered = _filter(all_rows, start, end)

    def fake_get_ohlc(*args, **kwargs):
        return filtered

    with patch.object(backtester_v3.db, "get_ohlc", side_effect=fake_get_ohlc):
        with patch.object(backtester_v3.db, "save_backtest_run", return_value=None):
            return backtester_v3.run_backtest_v3(symbol)


print("Walk-forward test — same config, three time windows\n")
symbols = get_watchlist()

for start, end, label in WINDOWS:
    print(f"=== {label} ===")
    rows = []
    for sym in symbols:
        r = run_window(sym, start, end)
        if r and r["total_trades"] > 0:
            rows.append(r)

    if not rows:
        print("  No trades in this window.\n")
        continue

    n = len(rows)
    avg_r = sum(r["avg_r_multiple"] for r in rows) / n
    avg_win = sum(r["win_rate_percent"] for r in rows) / n
    total_trades = sum(r["total_trades"] for r in rows)
    beats_bh = sum(
        1 for r in rows
        if r["total_return_percent"] > r["benchmark_return_percent"]
    )

    print(f"  symbols with trades : {n}")
    print(f"  total trades        : {total_trades}")
    print(f"  avg R-multiple      : {avg_r:+.2f}")
    print(f"  avg win rate        : {avg_win:.1f}%")
    print(f"  beat B&H            : {beats_bh}/{n}")
    print()