"""Fast vectorized walk-forward backtest."""
from __future__ import annotations

import pandas as pd

from analysis import indicators as ind
from database import db
from logging_config import get_logger
from strategy.rules import STRATEGIES

logger = get_logger(__name__)


def _trend(e20, e50, price):
    if pd.isna(e20) or pd.isna(e50):
        return "sideways"
    if price > e20 > e50:
        return "bullish"
    if price < e20 < e50:
        return "bearish"
    return "sideways"


def run_backtest(symbol: str, strategy_name: str = "default",
                 starting_capital: float = 100_000.0, min_bars: int = 40):
    rows = db.get_ohlc(symbol, limit_days=10000)
    if len(rows) < min_bars + 10:
        return None

    df = ind.to_dataframe(rows)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    ema20 = ind.ema(close, 20)
    ema50 = ind.ema(close, 50)
    rsi_s = ind.rsi(df)
    macd_line, macd_sig, _ = ind.macd(df)
    atr_s = ind.atr(df)
    stoch_k, _ = ind.stochastic(df)

    macd_diff = macd_line - macd_sig
    macd_prev = macd_diff.shift(1)
    cross_up = (macd_prev <= 0) & (macd_diff > 0)
    cross_dn = (macd_prev >= 0) & (macd_diff < 0)

    vol_avg20 = volume.rolling(20, min_periods=5).mean()
    sup = low.rolling(20, min_periods=5).min()
    res = high.rolling(20, min_periods=5).max()

    closes = close.values
    ema20v = ema20.values
    ema50v = ema50.values
    rsiv = rsi_s.values
    atrv = atr_s.values
    stochv = stoch_k.values
    macdup = cross_up.values
    macddn = cross_dn.values
    volavgv = vol_avg20.values
    volv = volume.values
    supv = sup.values
    resv = res.values
    dates = df["date"].values

    cash = starting_capital
    position = 0
    entry = 0.0
    equity_curve = []
    trades = []

    strategy_fn = STRATEGIES.get(strategy_name, STRATEGIES["default"])

    for i in range(min_bars, len(closes)):
        price = float(closes[i])
        trend = _trend(ema20v[i], ema50v[i], price)

        rsi_val = None if pd.isna(rsiv[i]) else round(float(rsiv[i]), 2)
        atr_val = None if pd.isna(atrv[i]) else float(atrv[i])
        stoch_val = None if pd.isna(stochv[i]) else float(stochv[i])

        if macdup[i]:
            macd_signal = "bullish_crossover"
        elif macddn[i]:
            macd_signal = "bearish_crossover"
        else:
            macd_signal = "none"

        vol_ratio = None
        if not pd.isna(volavgv[i]) and volavgv[i] > 0:
            vol_ratio = round(float(volv[i]) / float(volavgv[i]), 2)

        support = float(supv[i]) if not pd.isna(supv[i]) else price
        resistance = float(resv[i]) if not pd.isna(resv[i]) else price

        computed = {
            "price": price,
            "trend": trend,
            "rsi": rsi_val,
            "atr": atr_val,
            "stochastic_k": stoch_val,
            "macd_signal": macd_signal,
            "price_vs_ema20": "above" if not pd.isna(ema20v[i]) and price >= ema20v[i] else "below",
            "price_vs_ema50": "above" if not pd.isna(ema50v[i]) and price >= ema50v[i] else "below",
            "volume_vs_avg": vol_ratio,
            "support": support,
            "resistance": resistance,
            "as_of_date": str(dates[i]),
        }

        result = strategy_fn(computed)
        rec = result["recommendation"]

        if position == 0 and rec == "BUY":
            qty = int((cash * 0.95) // price)
            if qty > 0:
                cash -= qty * price
                position = qty
                entry = price
                trades.append({"side": "BUY", "price": price, "date": dates[i]})
        elif position > 0 and rec == "SELL":
            cash += position * price
            trades.append({
                "side": "SELL", "price": price, "date": dates[i],
                "pnl_pct": round((price - entry) / entry * 100, 2),
            })
            position = 0
            entry = 0.0

        equity_curve.append(cash + position * price)

    if position > 0:
        last = float(closes[-1])
        cash += position * last
        trades.append({
            "side": "SELL", "price": last, "date": dates[-1],
            "pnl_pct": round((last - entry) / entry * 100, 2) if entry else 0,
        })
        equity_curve.append(cash)

    closed = [t for t in trades if t["side"] == "SELL" and "pnl_pct" in t]
    wins = [t for t in closed if t["pnl_pct"] > 0]
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
        "strategy_version": strategy_name,
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