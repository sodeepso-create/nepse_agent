"""Run backtest v3 (paper-trader-aligned) on the watchlist."""
from __future__ import annotations
import time
from database import db
from tabulate import tabulate
from alerts.prefs import get_watchlist
from backtest.backtester_v3 import run_backtest_v3

rows = []
symbols = get_watchlist()
print(f"Backtesting v3 (aligned to paper trader) on {len(symbols)} symbols...\n")
t0 = time.time()
for i, sym in enumerate(symbols, 1):
    try:
        r = run_backtest_v3(sym)
        if not r:
            print(f"  [{i}/{len(symbols)}] {sym}: no data")
            continue
        rows.append({
            "symbol": sym, "trades": r["total_trades"],
            "win%": r["win_rate_percent"], "avgR": r["avg_r_multiple"],
            "return%": r["total_return_percent"],
            "maxDD%": r["max_drawdown_percent"],
            "B&H%": r["benchmark_return_percent"],
        })
        print(f"  [{i}/{len(symbols)}] {sym}: {r['total_return_percent']:+.2f}% ({r['total_trades']} trades, {r['win_rate_percent']}% win, avgR {r['avg_r_multiple']}, {r['max_drawdown_percent']}% DD) vs B&H {r['benchmark_return_percent']:+.2f}%")
    except Exception as e:
        print(f"  [{i}/{len(symbols)}] {sym}: ERROR {e}")

for r in rows:
    db.set_setting(f"DD_{r['symbol']}", str(r["maxDD%"]))
rows.sort(key=lambda x: x["return%"], reverse=True)
print("\n=== All symbols ===")
print(tabulate([list(r.values()) for r in rows], headers=list(rows[0].keys())))
n = len(rows)
beats_bh = sum(1 for r in rows if r["return%"] > r["B&H%"])
avg_win = sum(r["win%"] for r in rows) / n
avg_r = sum(r["avgR"] for r in rows) / n
avg_dd = sum(r["maxDD%"] for r in rows) / n
print("\n=== Summary ===")
print(f"  Symbols tested       : {n}")
print(f"  Beat buy-and-hold    : {beats_bh}/{n}")
print(f"  Avg win rate         : {avg_win:.1f}%")
print(f"  Avg R-multiple       : {avg_r:+.2f}")
print(f"  Avg max drawdown     : {avg_dd:.1f}%")
print(f"  Wall time            : {time.time() - t0:.0f}s")