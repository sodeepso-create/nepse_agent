"""Backtest the current strategy on every watchlist stock and rank results."""
from __future__ import annotations

import time

from tabulate import tabulate

from alerts.prefs import get_watchlist
from backtest.backtester import run_backtest
from database import db

rows = []
symbols = get_watchlist()
print(f"Backtesting {len(symbols)} symbols...")

t0 = time.time()
for i, sym in enumerate(symbols, 1):
    try:
        r = run_backtest(sym, strategy_name="default")
        if not r:
            print(f"  [{i}/{len(symbols)}] {sym}: no data")
            continue
        rows.append({
            "symbol": sym,
            "trades": r["total_trades"],
            "win%": r["win_rate_percent"],
            "return%": r["total_return_percent"],
            "maxDD%": r["max_drawdown_percent"],
        })
        print(f"  [{i}/{len(symbols)}] {sym}: {r['total_return_percent']}% "
              f"({r['total_trades']} trades, {r['max_drawdown_percent']}% DD)")
    except Exception as e:
        print(f"  [{i}/{len(symbols)}] {sym}: ERROR {e}")

rows.sort(key=lambda x: x["return%"], reverse=True)

print("\n=== TOP 15 (by return) ===")
print(tabulate([list(r.values()) for r in rows[:15]],
               headers=list(rows[0].keys()) if rows else []))

print("\n=== BOTTOM 10 ===")
print(tabulate([list(r.values()) for r in rows[-10:]],
               headers=list(rows[0].keys()) if rows else []))

with open("backtest_rank.csv", "w") as f:
    f.write("symbol,trades,win_pct,return_pct,maxdd_pct\n")
    for r in rows:
        f.write(f"{r['symbol']},{r['trades']},{r['win%']},{r['return%']},{r['maxDD%']}\n")

# Save each stock's drawdown to DB for position sizing
for r in rows:
    db.set_setting(f"DD_{r['symbol']}", str(r["maxDD%"]))

print(f"\nSaved {len(rows)} results to backtest_rank.csv and DB in {time.time()-t0:.0f}s")