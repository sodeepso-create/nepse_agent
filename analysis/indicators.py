"""Technical indicators computed from OHLC rows (no LLM guessing)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def to_dataframe(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    return df


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def _wilder_smooth(values: pd.Series, period: int) -> pd.Series:
    """Wilder's Running Moving Average — matches TradingView's ta.rma()
    and Wilder's 1978 book exactly. Seeds with SMA of first `period`."""
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    n = len(arr)
    out = np.full(n, np.nan)
    if n < period:
        return pd.Series(out, index=values.index)

    first_valid = 0
    while first_valid < n and np.isnan(arr[first_valid]):
        first_valid += 1
    if first_valid + period > n:
        return pd.Series(out, index=values.index)

    seed_idx = first_valid + period - 1
    out[seed_idx] = np.nanmean(arr[first_valid:seed_idx + 1])
    for i in range(seed_idx + 1, n):
        v = arr[i]
        if np.isnan(v):
            out[i] = out[i - 1]
        else:
            out[i] = (out[i - 1] * (period - 1) + v) / period
    return pd.Series(out, index=values.index)


def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = _wilder_smooth(gain, period)
    avg_loss = _wilder_smooth(loss, period)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(df: pd.DataFrame, fast=12, slow=26, signal=9):
    line = ema(df["close"], fast) - ema(df["close"], slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = line - sig
    return line, sig, hist


def bollinger(df: pd.DataFrame, window=20, num_std=2.0):
    mid = sma(df["close"], window)
    std = df["close"].rolling(window=window, min_periods=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower) / mid.replace(0, np.nan)
    return mid, upper, lower, width


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return _wilder_smooth(tr, period)


def stochastic(df: pd.DataFrame, k_period=14, d_period=3):
    low_min = df["low"].rolling(k_period, min_periods=k_period).min()
    high_max = df["high"].rolling(k_period, min_periods=k_period).max()
    k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    d = k.rolling(d_period, min_periods=d_period).mean()
    return k, d


def support_resistance(df: pd.DataFrame, lookback: int = 20):
    window = df.tail(lookback)
    return float(window["low"].min()), float(window["high"].max())


def detect_trend(ema20, ema50, price) -> str:
    if pd.isna(ema20) or pd.isna(ema50):
        return "sideways"
    if price > ema20 > ema50:
        return "bullish"
    if price < ema20 < ema50:
        return "bearish"
    return "sideways"


def macd_crossover(macd_line: pd.Series, signal: pd.Series) -> str:
    if len(macd_line) < 2 or len(signal) < 2:
        return "none"
    prev_diff = macd_line.iloc[-2] - signal.iloc[-2]
    curr_diff = macd_line.iloc[-1] - signal.iloc[-1]
    if prev_diff <= 0 < curr_diff:
        return "bullish_crossover"
    if prev_diff >= 0 > curr_diff:
        return "bearish_crossover"
    return "none"


def compute_all(rows: list[dict], min_bars: int = 30) -> dict | None:
    df = to_dataframe(rows)
    if df.empty or len(df) < min_bars:
        return None

    close = df["close"]
    price = float(close.iloc[-1])

    ema20 = ema(close, 20)
    ema50 = ema(close, 50) if len(df) >= 50 else ema(close, min(30, len(df)))
    rsi_s = rsi(df)
    macd_line, macd_sig, macd_hist = macd(df)
    bb_up, bb_lo, bb_width = None, None, None
    try:
        bb_mid, bb_up, bb_lo, bb_width = bollinger(df)
    except Exception:
        pass
    atr_s = atr(df)
    stoch_k, stoch_d = stochastic(df)

    e20 = float(ema20.iloc[-1]) if not pd.isna(ema20.iloc[-1]) else None
    e50 = float(ema50.iloc[-1]) if not pd.isna(ema50.iloc[-1]) else None
    rsi_val = float(rsi_s.iloc[-1]) if not pd.isna(rsi_s.iloc[-1]) else None

    vol_now = float(df["volume"].iloc[-1])
    vol_avg = float(df["volume"].tail(20).mean())
    vol_ratio = round(vol_now / vol_avg, 2) if vol_avg > 0 else None

    support, resistance = support_resistance(df)
    trend = detect_trend(e20, e50, price) if e20 and e50 else "sideways"

    return {
        "as_of_date": str(df["date"].iloc[-1]) if "date" in df.columns else None,
        "price": round(price, 2),
        "ema20": round(e20, 2) if e20 is not None else None,
        "ema50": round(e50, 2) if e50 is not None else None,
        "rsi": round(rsi_val, 2) if rsi_val is not None else None,
        "macd": round(float(macd_line.iloc[-1]), 4) if not pd.isna(macd_line.iloc[-1]) else None,
        "macd_signal": macd_crossover(macd_line, macd_sig),
        "macd_hist": round(float(macd_hist.iloc[-1]), 4) if not pd.isna(macd_hist.iloc[-1]) else None,
        "bb_upper": round(float(bb_up.iloc[-1]), 2) if bb_up is not None and not pd.isna(bb_up.iloc[-1]) else None,
        "bb_lower": round(float(bb_lo.iloc[-1]), 2) if bb_lo is not None and not pd.isna(bb_lo.iloc[-1]) else None,
        "bb_width": round(float(bb_width.iloc[-1]), 4) if bb_width is not None and not pd.isna(bb_width.iloc[-1]) else None,
        "atr": round(float(atr_s.iloc[-1]), 2) if not pd.isna(atr_s.iloc[-1]) else None,
        "stochastic_k": round(float(stoch_k.iloc[-1]), 2) if not pd.isna(stoch_k.iloc[-1]) else None,
        "stochastic_d": round(float(stoch_d.iloc[-1]), 2) if not pd.isna(stoch_d.iloc[-1]) else None,
        "trend": trend,
        "price_vs_ema20": "above" if e20 and price >= e20 else "below",
        "price_vs_ema50": "above" if e50 and price >= e50 else "below",
        "volume_vs_avg": vol_ratio,
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "bars": len(df),
    }