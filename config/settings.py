"""Centralized configuration loaded from .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get(key: str, default=None, required=False):
    val = os.getenv(key, default)
    if required and val is None:
        raise RuntimeError(
            f"Missing required setting '{key}'. Copy .env.example to .env and fill it in."
        )
    return val


DB_PATH = str(BASE_DIR / _get("DB_PATH", "./data/nepse_agent.db"))
COLLECTION_INTERVAL_MINUTES = int(_get("COLLECTION_INTERVAL_MINUTES", 15))
WATCHLIST = [
    t.strip().upper()
    for t in _get("WATCHLIST", "NABIL,NICA,HIDCL,NTC,UPPER").split(",")
    if t.strip()
]

REQUEST_TIMEOUT_SECONDS = int(_get("REQUEST_TIMEOUT_SECONDS", 20))
REQUEST_DELAY_SECONDS = float(_get("REQUEST_DELAY_SECONDS", 1.5))

LOG_LEVEL = _get("LOG_LEVEL", "INFO")
LOG_FILE = str(BASE_DIR / _get("LOG_FILE", "./logs/nepse_agent.log"))

MAX_POSITION_SIZE_PERCENT = float(_get("MAX_POSITION_SIZE_PERCENT", 5))
MAX_DAILY_LOSS_PERCENT = float(_get("MAX_DAILY_LOSS_PERCENT", 2))
PAPER_STARTING_CAPITAL = float(_get("PAPER_STARTING_CAPITAL", 1_000_000))
ALERT_EMAIL_FROM = _get("ALERT_EMAIL_FROM", "")
ALERT_EMAIL_TO = _get("ALERT_EMAIL_TO", "")
ALERT_EMAIL_APP_PASSWORD = _get("ALERT_EMAIL_APP_PASSWORD", "")
ALERT_EMAIL_TO_2 = _get("ALERT_EMAIL_TO_2", "")
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


MY_HOLDINGS = _parse_holdings(_get("MY_HOLDINGS", ""))
import re as _re

def _parse_price_alerts(raw: str) -> list[dict]:
    out = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        m = _re.match(r"^([A-Za-z]+)([<>])([+-]?\d+(?:\.\d+)?)$", part)
        if not m:
            continue
        sym, op, val = m.group(1).upper(), m.group(2), m.group(3)
        is_pct = val.startswith(("+", "-"))
        out.append({
            "symbol": sym,
            "op": op,
            "value": float(val.replace("+", "")),
            "is_pct": is_pct,
        })
    return out


PRICE_ALERTS = _parse_price_alerts(_get("PRICE_ALERTS", ""))
PROFITABLE_STOCKS = [
    t.strip().upper()
    for t in _get("PROFITABLE_STOCKS", "").split(",")
    if t.strip()
]
USE_LLM_CLASSIFIER = _get("USE_LLM_CLASSIFIER", "false").lower() == "true"
LLM_MODEL = _get("LLM_MODEL", "qwen2.5:7b")