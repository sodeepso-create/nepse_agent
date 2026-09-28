"""Read/write user preferences (holdings, price alerts) from DB, fallback to .env."""
from __future__ import annotations

import re

from config import settings
from database import db


def _parse_holdings(raw: str) -> dict[str, int]:
    out = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        sym, _, qty = part.partition(":")
        try:
            out[sym.strip().upper()] = int(qty.strip())
        except ValueError:
            continue
    return out


def _parse_price_alerts(raw: str) -> list[dict]:
    out = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^([A-Za-z]+)([<>])([+-]?\d+(?:\.\d+)?)$", part)
        if not m:
            continue
        sym, op, val = m.group(1).upper(), m.group(2), m.group(3)
        is_pct = val.startswith(("+", "-"))
        out.append({
            "symbol": sym, "op": op,
            "value": float(val.replace("+", "")),
            "is_pct": is_pct,
        })
    return out


def get_holdings() -> dict[str, int]:
    raw = db.get_setting("MY_HOLDINGS", "")
    if raw:
        return _parse_holdings(raw)
    return settings.MY_HOLDINGS


def set_holdings(d: dict[str, int]):
    raw = ",".join(f"{s}:{q}" for s, q in d.items())
    db.set_setting("MY_HOLDINGS", raw)


def get_price_alerts() -> list[dict]:
    raw = db.get_setting("PRICE_ALERTS", "")
    if raw:
        return _parse_price_alerts(raw)
    return settings.PRICE_ALERTS


def set_price_alerts(raw: str):
    db.set_setting("PRICE_ALERTS", raw)


def get_watchlist() -> list[str]:
    raw = db.get_setting("WATCHLIST", "")
    if raw:
        return [s.strip().upper() for s in raw.split(",") if s.strip()]
    return list(settings.WATCHLIST)


def set_watchlist(symbols: list[str]):
    db.set_setting("WATCHLIST", ",".join(s.upper() for s in symbols))


def get_profitable() -> list[str]:
    raw = db.get_setting("PROFITABLE_STOCKS", "")
    if raw:
        return [s.strip().upper() for s in raw.split(",") if s.strip()]
    return list(settings.PROFITABLE_STOCKS)


def set_profitable(symbols: list[str]):
    db.set_setting("PROFITABLE_STOCKS", ",".join(s.upper() for s in symbols))