"""Outgoing email: password resets and new-account alerts for the board.

If SMTP settings are present in the course-root .env, mail is sent for real:
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=you@gmail.com
    SMTP_PASSWORD=<Gmail app password>
    MAIL_FROM=AFLAX Alumni <you@gmail.com>        (optional; defaults to SMTP_USER)
Otherwise each message is written to data/outbox/ as an .eml file (open it in Mail),
so every email flow works locally without credentials.

APP_URL sets the site address used in links (default http://localhost:8001).
"""

import logging
import os
import re
import smtplib
from datetime import datetime
from email.message import EmailMessage

import config  # noqa: F401  (loads the .env files)
from db import OUTBOX_DIR

log = logging.getLogger("aflax.mail")

APP_URL = os.getenv("APP_URL", "http://localhost:8001").rstrip("/")


def _build(to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = os.getenv("MAIL_FROM") or os.getenv("SMTP_USER") or "AFLAX Alumni <no-reply@aflax.local>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send_email(to: str, subject: str, body: str) -> None:
    """Send (or save to the outbox). Never raises: a mail failure must not break a request."""
    msg = _build(to, subject, body)
    host = os.getenv("SMTP_HOST")
    try:
        if host:
            with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as smtp:
                smtp.starttls()
                smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                smtp.send_message(msg)
            log.info("Sent email to %s: %s", to, subject)
        else:
            OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^a-z0-9]+", "-", f"{to}-{subject}".lower()).strip("-")[:60]
            path = OUTBOX_DIR / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{slug}.eml"
            path.write_bytes(bytes(msg))
            log.warning("SMTP not configured; saved email to %s", path)
    except Exception:
        log.exception("Failed to send email to %s", to)


def password_reset_email(to: str, first_name: str, token: str) -> None:
    link = f"{APP_URL}/reset-password?token={token}"
    send_email(
        to,
        "Reset your AFLAX Alumni password",
        f"Hi {first_name},\n\n"
        f"Someone (hopefully you) asked to reset your AFLAX Alumni Connections password.\n"
        f"Use this link within the next hour:\n\n{link}\n\n"
        f"If you didn't ask for this, you can ignore this email; your password won't change.\n\n"
        f"Go Falcons!\nAFLAX Alumni Board",
    )


def new_account_alert(admin_emails: list[str], applicant: dict) -> None:
    who = f"{applicant['first_name']} {applicant['last_name']}"
    details = " · ".join(filter(None, [
        f"Class of {applicant['grad_year']}", applicant["status"], applicant.get("rank"),
        applicant.get("afsc"), applicant.get("base") or applicant.get("city"),
    ]))
    for to in admin_emails:
        send_email(
            to,
            f"New AFLAX account request: {who}",
            f"A new member is waiting for board approval:\n\n"
            f"  {who} <{applicant['email']}>\n  {details}\n\n"
            f"Review it here: {APP_URL}/admin\n",
        )
