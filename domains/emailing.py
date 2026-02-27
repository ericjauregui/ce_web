from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_order_email(subject: str, body: str, csv_bytes: bytes, filename: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587") or "587")
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()
    email_to = os.getenv("EMAIL_TO", "").strip()
    email_from = os.getenv("EMAIL_FROM", smtp_user).strip()

    if not (smtp_host and smtp_user and smtp_pass and email_to and email_from):
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = email_from
    message["To"] = email_to
    message.set_content(body)
    message.add_attachment(csv_bytes, maintype="text", subtype="csv", filename=filename)

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_pass)
        smtp.send_message(message)

    return True
