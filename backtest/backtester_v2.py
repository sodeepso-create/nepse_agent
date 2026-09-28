"""Backtest v2 — EMA20/EMA50 crossover."""
from __future__ import annotations

import pandas as pd

from analysis import indicators as ind
from backtest.strategy_v2 import compute_signals, position_size
from database import db
from logging_config import get_logger

logger = get_logger(__name__)


def run_backtest_v2(symbol: str, starting_capital: float = 100_000.0,
                    min_bars: int = 60):
    rows = db.get_ohlc(symbol, limit_days=10000)
    if len(rows) < min_bars + 10:
        return None

    df = ind.to_dataframe(rows)
    df = compute_signals(df)

    cash = starting_capital
    position = 0
    entry = 0.0
    equity_curve = []
    trades = []

    for i in range(min_bars, len(df)):
        row = df.iloc[i]
        price = float(row["close"])
        date = row["date"]

        if position > 0 and bool(row["exit_signal"]):
            cash += position * price
            pnl_pct = (price - entry) / entry * 100
            trades.append({
                "side": "SELL", "price": price, "date": date,
                "pnl_pct": round(pnl_pct, 2), "reason": "ema_cross_down",
            })
            position = 0
            entry = 0.0

        if position == 0 and bool(row["entry_signal"]):
            qty = position_size(cash, price)
            if qty > 0:
                cash -= qty * price
                position = qty
                entry = price
                trades.append({"side": "BUY", "price": price, "date": date})

        equity = cash + position * price
        equity_curve.append(equity)

    if position > 0:
        last_price = float(df.iloc[-1]["close"])
        cash += position * last_price
        pnl_pct = (last_price - entry) / entry * 100
        trades.append({
            "side": "SELL", "price": last_price, "date": df.iloc[-1]["date"],
            "pnl_pct": round(pnl_pct, 2), "reason": "end_of_data",
        })
        equity_curve.append(cash)

    closed = [t for t in trades if t["side"] == "SELL"]
    wins = [t for t in closed if t.get("pnl_pct", 0) > 0]
    win_rate = (len(wins) / len(closed) * 100) if closed else 0.0
    total_return = (cash - starting_capital) / starting_capital * 100

    peak = starting_capital
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)

    result = {
        "symbol": symbol.upper(),
        "strategy_version": "v2-ema",
        "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"],
        "total_trades": len(closed),
        "win_rate_percent": round(win_rate, 2),
        "total_return_percent": round(total_return, 2),
        "max_drawdown_percent": round(max_dd, 2),
        "final_capital": round(cash, 2),
    }
    try:
        db.save_backtest_run(result)
    except Exception as e:
        logger.warning("Could not persist backtest run: %s", e)
    return result