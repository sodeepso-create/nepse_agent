"""Send alert emails via Gmail SMTP."""
from __future__ import annotations

import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import settings
from logging_config import get_logger

logger = get_logger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_email(subject: str, body: str) -> bool:
    if not (settings.ALERT_EMAIL_FROM and settings.ALERT_EMAIL_TO
            and settings.ALERT_EMAIL_APP_PASSWORD):
        logger.warning("Email not configured — skipping send")
        return False

    msg = MIMEMultipart()
    msg["From"] = settings.ALERT_EMAIL_FROM
    recipients = [settings.ALERT_EMAIL_TO]
    if settings.ALERT_EMAIL_TO_2:
        recipients.append(settings.ALERT_EMAIL_TO_2)
    msg["To"] = ", ".join(recipients)
    actual_recipients = recipients
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(settings.ALERT_EMAIL_FROM, settings.ALERT_EMAIL_APP_PASSWORD)
            server.send_message(msg, to_addrs=actual_recipients)
        logger.info("Email sent: %s", subject)
        time.sleep(2)
        return True
    except Exception as e:
        logger.error("Email failed: %s", e)
        return False