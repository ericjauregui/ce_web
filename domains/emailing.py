from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr


def _normalized_email(value: str) -> str:
    parsed = parseaddr((value or "").strip())[1].strip()
    if not parsed or "@" not in parsed:
        return ""
    return parsed


def send_order_email(
    subject: str,
    body: str,
    csv_bytes: bytes,
    filename: str,
    client_email: str = "",
    html_body: str = "",
) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587") or "587")
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()
    email_to = os.getenv("EMAIL_TO", "").strip()
    email_from = os.getenv("EMAIL_FROM", smtp_user).strip()

    if not (smtp_host and smtp_user and smtp_pass and email_to and email_from):
        return False

    primary_recipient = _normalized_email(email_to)
    sender_email = _normalized_email(email_from)
    customer_email = _normalized_email(client_email)

    if not (primary_recipient and sender_email):
        return False

    to_recipients: list[str] = [primary_recipient]
    if customer_email and customer_email not in to_recipients:
        to_recipients.append(customer_email)

    cc_recipients: list[str] = []
    if sender_email not in to_recipients:
        cc_recipients.append(sender_email)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = ", ".join(to_recipients)
    if cc_recipients:
        message["Cc"] = ", ".join(cc_recipients)
    message.set_content(body)
    if html_body.strip():
        message.add_alternative(html_body, subtype="html")
    message.add_attachment(csv_bytes, maintype="text", subtype="csv", filename=filename)

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_pass)
        smtp.send_message(message)

    return True
