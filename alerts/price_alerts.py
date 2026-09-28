"""Check price triggers and send email alerts."""
from __future__ import annotations

from alerts.email_sender import send_email
from alerts.prefs import get_price_alerts
from database import db
from logging_config import get_logger

logger = get_logger(__name__)


def _latest_price(symbol: str) -> float | None:
    rows = db.get_ohlc(symbol, limit_days=5)
    if not rows:
        return None
    return float(rows[-1]["close"])


def _prev_price(symbol: str) -> float | None:
    rows = db.get_ohlc(symbol, limit_days=5)
    if len(rows) < 2:
        return None
    return float(rows[-2]["close"])


def run_price_alerts() -> int:
    triggers = get_price_alerts()
    if not triggers:
        return 0

    sent = 0
    for t in triggers:
        sym = t["symbol"]
        price = _latest_price(sym)
        prev = _prev_price(sym)
        if price is None:
            continue

        hit = False
        detail = ""

        if t["is_pct"]:
            if prev is None or prev == 0:
                continue
            change_pct = (price - prev) / prev * 100
            if t["op"] == ">" and change_pct > t["value"]:
                hit = True
                detail = f"up {change_pct:+.2f}% today"
            elif t["op"] == "<" and change_pct < t["value"]:
                hit = True
                detail = f"down {change_pct:+.2f}% today"
        else:
            if t["op"] == ">" and price > t["value"]:
                hit = True
                detail = f"above {t['value']}"
            elif t["op"] == "<" and price < t["value"]:
                hit = True
                detail = f"below {t['value']}"

        if not hit:
            continue

        url = f"price:{sym}:{t['op']}:{t['value']}"
        if db.was_alert_sent(url):
            continue

        subject = f"NEPSE price alert: {sym} {detail}"
        body = (
            f"Price alert triggered:\n\n"
            f"Symbol: {sym}\n"
            f"Current price: {price}\n"
            f"Trigger: {sym}{t['op']}{t['value']}\n"
            f"Detail: {detail}\n\n"
            f"—— NEPSE Agent"
        )

        if send_email(subject, body):
            db.mark_alert_sent(url)
            sent += 1
            print(f"  ✓ Price alert sent: {sym} {detail}")

    return sent