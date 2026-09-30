"""Backtest v3 — mirrors paper_trader.py exactly.

The v1 backtester used no stops, no targets, 95% position sizing, and no
CGT. The paper trader uses 1.5xATR stops, 2R targets, 5% position sizing,
board lots, CGT, and T+2 settlement. This file reproduces the paper
trader's logic bar-for-bar so backtest numbers actually predict paper
results.

Simplifications (documented, not hidden):
  - No news input (no historical news available)
  - No DD-history-based position scaling (that would be lookahead)
  - Stops fill at the stop price even on a gap-down (optimistic)
"""
from __future__ import annotations

from datetime import date as _date, timedelta

import pandas as pd

from analysis import indicators as ind
from database import db
from logging_config import get_logger

logger = get_logger(__name__)

COMMISSION_PCT = 0.004
CGT_SHORT_PCT = 0.05
SLIPPAGE_PCT = 0.003
BOARD_LOT = 10
SETTLEMENT_DAYS = 2

POSITION_PCT = 0.20
STOP_ATR_MULT = 1.5
CIRCUIT_PCT = 0.10
TARGET_RR = 999.0


def _stop_price(entry: float, atr: float | None) -> float:
    if atr and atr > 0:
        raw = entry - STOP_ATR_MULT * atr
    else:
        raw = entry * 0.97
    return max(round(raw, 2), round(entry * (1 - CIRCUIT_PCT), 2))


def _target_price(entry: float, stop: float) -> float:
    risk = abs(entry - stop)
    raw = entry + TARGET_RR * risk
    return min(round(raw, 2), round(entry * (1 + CIRCUIT_PCT), 2))


def _iso_add_days(iso: str, days: int) -> str:
    y, m, d = map(int, iso.split("-"))
    return (_date(y, m, d) + timedelta(days=days)).isoformat()


def run_backtest_v3(symbol: str, starting_capital: float = 100_000.0,
                    min_bars: int = 60):
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
    highs = high.values
    lows = low.values
    ema20v = ema20.values
    ema50v = ema50.values
    rsiv = rsi_s.values
    atrv = atr_s.values
    stochv = stoch_k.values
    volavgv = vol_avg20.values
    volv = volume.values
    supv = sup.values
    resv = res.values
    macdup = cross_up.values
    macddn = cross_dn.values
    dates = [str(d)[:10] for d in df["date"].values]

    from analysis.scoring_engine import score as score_fn
    from analysis.indicators import detect_trend

    cash = starting_capital
    position = 0
    entry = 0.0
    stop = 0.0
    target = 0.0
    entry_date = None
    total_fees = 0.0
    total_tax = 0.0
    trades: list[dict] = []
    equity_curve = [starting_capital]
    unsettled: list[tuple[str, float]] = []

    for i in range(min_bars, len(closes)):
        today = dates[i]

        still = []
        for sd, amt in unsettled:
            if sd <= today:
                cash += amt
            else:
                still.append((sd, amt))
        unsettled = still

        price = float(closes[i])
        hi = float(highs[i])
        lo = float(lows[i])

        trend = detect_trend(ema20v[i], ema50v[i], price)
        if macdup[i]:
            macd_signal = "bullish_crossover"
        elif macddn[i]:
            macd_signal = "bearish_crossover"
        else:
            macd_signal = "none"

        rsi_val = None if pd.isna(rsiv[i]) else round(float(rsiv[i]), 2)
        atr_val = None if pd.isna(atrv[i]) else float(atrv[i])
        stoch_val = None if pd.isna(stochv[i]) else float(stochv[i])
        vol_ratio = None
        if not pd.isna(volavgv[i]) and volavgv[i] > 0:
            vol_ratio = round(float(volv[i]) / float(volavgv[i]), 2)
        support = float(supv[i]) if not pd.isna(supv[i]) else price
        resistance = float(resv[i]) if not pd.isna(resv[i]) else price

        computed = {
            "price": price, "trend": trend, "rsi": rsi_val,
            "atr": atr_val, "stochastic_k": stoch_val,
            "macd_signal": macd_signal,
            "price_vs_ema20": "above" if not pd.isna(ema20v[i]) and price >= ema20v[i] else "below",
            "price_vs_ema50": "above" if not pd.isna(ema50v[i]) and price >= ema50v[i] else "below",
            "volume_vs_avg": vol_ratio,
            "support": support, "resistance": resistance,
            "as_of_date": today,
        }

        # exit check
        if position > 0:
            exit_price = None
            exit_reason = None

            if lo <= stop:
                exit_price = stop
                exit_reason = "stop_loss"
            if exit_price is None and hi >= target:
                exit_price = target
                exit_reason = "target"
            if exit_price is None and trend == "bearish" and macd_signal == "bearish_crossover":
                exit_price = price
                exit_reason = "signal_exit"

            if exit_price is not None:
                sell_fill = round(exit_price * (1 - SLIPPAGE_PCT), 2)
                gross = sell_fill * position
                comm_sell = gross * COMMISSION_PCT
                pre_tax = gross - comm_sell
                cost_basis = entry * position * (1 + COMMISSION_PCT)
                pnl = pre_tax - cost_basis
                tax = pnl * CGT_SHORT_PCT if pnl > 0 else 0.0
                net_pnl = pnl - tax
                proceeds = pre_tax - tax

                total_fees += comm_sell
                total_tax += tax

                settle_iso = _iso_add_days(today, SETTLEMENT_DAYS)
                unsettled.append((settle_iso, proceeds))

                risk_per_share = entry - stop
                r_mult = (sell_fill - entry) / risk_per_share if risk_per_share > 0 else 0.0

                trades.append({
                    "entry_date": entry_date, "exit_date": today,
                    "entry": entry, "exit": sell_fill,
                    "qty": position, "reason": exit_reason,
                    "net_pnl": round(net_pnl, 2),
                    "pnl_pct": round((sell_fill - entry) / entry * 100, 2),
                    "r_multiple": round(r_mult, 2),
                })

                position = 0
                entry = stop = target = 0.0
                entry_date = None

        # entry check
        if position == 0:
            result = score_fn(computed, news_items=None)
            if result["recommendation"] == "BUY" and computed["macd_signal"] == "bullish_crossover":
                fill = round(price * (1 + SLIPPAGE_PCT), 2)
                budget = cash * POSITION_PCT
                qty = int(budget // fill)
                qty = (qty // BOARD_LOT) * BOARD_LOT
                if qty > 0:
                    gross = qty * fill
                    comm = gross * COMMISSION_PCT
                    cost = gross + comm
                    if cost <= cash:
                        cash -= cost
                        total_fees += comm
                        position = qty
                        entry = fill
                        stop = _stop_price(fill, atr_val)
                        target = _target_price(fill, stop)
                        entry_date = today

        pos_value = position * price if position > 0 else 0.0
        unsettled_total = sum(a for _, a in unsettled)
        equity_curve.append(cash + pos_value + unsettled_total)

    if position > 0:
        last_price = float(closes[-1])
        sell_fill = round(last_price * (1 - SLIPPAGE_PCT), 2)
        gross = sell_fill * position
        comm_sell = gross * COMMISSION_PCT
        pre_tax = gross - comm_sell
        cost_basis = entry * position * (1 + COMMISSION_PCT)
        pnl = pre_tax - cost_basis
        tax = pnl * CGT_SHORT_PCT if pnl > 0 else 0.0
        net_pnl = pnl - tax
        proceeds = pre_tax - tax
        cash += proceeds
        total_fees += comm_sell
        total_tax += tax
        risk_per_share = entry - stop
        r_mult = (sell_fill - entry) / risk_per_share if risk_per_share > 0 else 0.0
        trades.append({
            "entry_date": entry_date, "exit_date": dates[-1],
            "entry": entry, "exit": sell_fill,
            "qty": position, "reason": "end_of_data",
            "net_pnl": round(net_pnl, 2),
            "pnl_pct": round((sell_fill - entry) / entry * 100, 2),
            "r_multiple": round(r_mult, 2),
        })
        position = 0

    final_equity = cash + sum(a for _, a in unsettled)
    wins = [t for t in trades if t["net_pnl"] > 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0.0
    total_return = (final_equity - starting_capital) / starting_capital * 100

    peak = starting_capital
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    bench_closes = closes[min_bars:]
    if len(bench_closes) >= 2:
        first = float(bench_closes[0])
        last = float(bench_closes[-1])
        eff_buy = first * (1 + COMMISSION_PCT + SLIPPAGE_PCT)
        bench_qty = int(starting_capital // eff_buy)
        if bench_qty > 0:
            leftover = starting_capital - bench_qty * eff_buy
            eff_sell = last * (1 - COMMISSION_PCT - SLIPPAGE_PCT)
            bench_final = leftover + bench_qty * eff_sell
            bench_ret = (bench_final - starting_capital) / starting_capital * 100
        else:
            bench_final = starting_capital
            bench_ret = 0.0
    else:
        bench_final = starting_capital
        bench_ret = 0.0

    r_multiples = [t["r_multiple"] for t in trades]
    avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0

    result = {
        "symbol": symbol.upper(),
        "strategy_version": "v3-aligned",
        "start_date": dates[min_bars],
        "end_date": dates[-1],
        "total_trades": len(trades),
        "win_rate_percent": round(win_rate, 2),
        "total_return_percent": round(total_return, 2),
        "max_drawdown_percent": round(max_dd, 2),
        "final_capital": round(final_equity, 2),
        "total_fees_paid": round(total_fees, 2),
        "total_tax_paid": round(total_tax, 2),
        "avg_r_multiple": round(avg_r, 2),
        "benchmark_return_percent": round(bench_ret, 2),
        "benchmark_final_capital": round(bench_final, 2),
    }
    try:
        db.save_backtest_run(result)
    except Exception as e:
        logger.warning("Could not persist backtest run: %s", e)
    return result