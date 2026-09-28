"""Strategy v2 — EMA20/EMA50 crossover trend follower."""
from __future__ import annotations

import pandas as pd


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with entry_signal / exit_signal columns."""
    df = df.copy()
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["diff"] = df["ema20"] - df["ema50"]
    df["prev_diff"] = df["diff"].shift(1)

    df["entry_signal"] = (df["prev_diff"] <= 0) & (df["diff"] > 0)
    df["exit_signal"] = (df["prev_diff"] >= 0) & (df["diff"] < 0)
    return df


def position_size(equity: float, entry_price: float,
                  max_pct: float = 0.95) -> int:
    if entry_price <= 0 or equity <= 0:
        return 0
    return int((equity * max_pct) // entry_price)