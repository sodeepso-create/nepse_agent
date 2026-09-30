"""Fast vectorized walk-forward backtest with realistic costs."""
from __future__ import annotations

import pandas as pd

from analysis import indicators as ind
from database import db
from logging_config import get_logger
from strategy.rules import STRATEGIES

logger = get_logger(__name__)


# Cost model — NEPSE broker commission + SEBON + DP charges ≈ 0.4% per side.
# Slippage: for illiquid stocks, real fills differ from close. 0.3% per side
# is a conservative default.
DEFAULT_COMMISSION_PCT = 0.4
DEFAULT_SLIPPAGE_PCT = 0.3


def _trend(e20, e50, price):
    if pd.isna(e20) or pd.isna(e50):
        return "sideways"
    if price > e20 > e50:
        return "bullish"
    if price < e20 < e50:
        return "bearish"
    return "sideways"


def _buy_and_hold_benchmark(closes, starting_capital: float, per_side_cost: float):
    """Buy on first bar, hold to last. Applies entry and exit costs."""
    if len(closes) < 2:
        return None
    first = float(closes[0])
    last = float(closes[-1])
    effective_buy = first * (1 + per_side_cost)
    qty = int(starting_capital // effective_buy)
    if qty <= 0:
        return None
    cash_spent = qty * effective_buy
    leftover = starting_capital - cash_spent
    effective_sell = last * (1 - per_side_cost)
    final = leftover + qty * effective_sell
    ret = (final - starting_capital) / starting_capital * 100
    return {
        "buy_price": round(first, 2),
        "sell_price": round(last, 2),
        "final_capital": round(final, 2),
        "total_return_percent": round(ret, 2),
    }


def run_backtest(
    symbol: str,
    strategy_name: str = "default",
    starting_capital: float = 100_000.0,
    min_bars: int = 40,
    commission_pct: float = DEFAULT_COMMISSION_PCT,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
):
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

    per_side_cost = (commission_pct + slippage_pct) / 100.0

    cash = starting_capital
    position = 0
    entry = 0.0
    total_fees_paid = 0.0
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
            effective_buy_price = price * (1 + per_side_cost)
            qty = int((cash * 0.95) // effective_buy_price)
            if qty > 0:
                fee_cost = qty * (effective_buy_price - price)
                cash -= qty * effective_buy_price
                total_fees_paid += fee_cost
                position = qty
                entry = price
                trades.append({
                    "side": "BUY",
                    "price": price,
                    "date": dates[i],
                    "qty": qty,
                    "fee": round(fee_cost, 2),
                })
        elif position > 0 and rec == "SELL":
            effective_sell_price = price * (1 - per_side_cost)
            fee_cost = position * (price - effective_sell_price)
            cash += position * effective_sell_price
            total_fees_paid += fee_cost
            trades.append({
                "side": "SELL",
                "price": price,
                "date": dates[i],
                "qty": position,
                "fee": round(fee_cost, 2),
                "pnl_pct": round((price - entry) / entry * 100, 2),
            })
            position = 0
            entry = 0.0

        equity_curve.append(cash + position * price)

    if position > 0:
        last = float(closes[-1])
        effective_sell_price = last * (1 - per_side_cost)
        fee_cost = position * (last - effective_sell_price)
        cash += position * effective_sell_price
        total_fees_paid += fee_cost
        trades.append({
            "side": "SELL",
            "price": last,
            "date": dates[-1],
            "qty": position,
            "fee": round(fee_cost, 2),
            "pnl_pct": round((last - entry) / entry * 100, 2) if entry else 0,
        })
        equity_curve.append(cash)
        position = 0

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

    benchmark = _buy_and_hold_benchmark(
        closes[min_bars:], starting_capital, per_side_cost
    )

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
        "total_fees_paid": round(total_fees_paid, 2),
        "commission_pct": commission_pct,
        "slippage_pct": slippage_pct,
        "benchmark_return_percent": benchmark["total_return_percent"] if benchmark else None,
        "benchmark_final_capital": benchmark["final_capital"] if benchmark else None,
    }
    try:
        db.save_backtest_run(result)
    except Exception as e:
        logger.warning("Could not persist backtest run: %s", e)
    return result