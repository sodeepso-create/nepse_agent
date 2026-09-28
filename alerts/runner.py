"""Run alert checks and send emails."""
from __future__ import annotations

from alerts.corporate_actions import find_corporate_actions
from alerts.email_sender import send_email
from alerts.market_actions import run_market_action_alerts
from alerts.prefs import get_holdings
from alerts.price_alerts import run_price_alerts
from database import db
from logging_config import get_logger

logger = get_logger(__name__)

def run_alerts():
    holdings = get_holdings()
    if not holdings:
        print("MY_HOLDINGS is empty in .env — no corporate action alerts.")
        print("Example: MY_HOLDINGS=NABIL:100,NICA:0,SCB:50")
        hits = []
    else:
        hits = find_corporate_actions()

    sent = 0
    for h in hits:
        url = h.get("url") or h["headline"]
        if db.was_alert_sent(url):
            continue

        syms = ", ".join(
            f"{s} (you hold {holdings.get(s, 0)})" for s in h["symbols"]
        )
        subject = f"NEPSE alert: {'/'.join(h['actions']).title()} — {', '.join(h['symbols'])}"
        body = (
            f"Corporate action detected for your holdings:\n\n"
            f"Symbols: {syms}\n"
            f"Action: {', '.join(h['actions'])}\n"
            f"Date: {h.get('date') or 'unknown'}\n\n"
            f"Headline:\n  {h['headline']}\n\n"
            f"Source: {h.get('url') or 'n/a'}\n\n"
            f"—— NEPSE Agent"
        )

        if send_email(subject, body):
            db.mark_alert_sent(url)
            sent += 1
            print(f"  ✓ Alert sent: {h['headline'][:80]}")

    sent += run_price_alerts()
    market_hits = run_market_action_alerts()
    sent += market_hits

    print(f"\nSent {sent} alert(s) total "
          f"({len(hits)} holdings, {market_hits} market actions).")
    return sent