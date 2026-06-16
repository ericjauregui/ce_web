from __future__ import annotations

import csv
import base64
import io
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr, make_msgid, parseaddr
from html import escape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from domains.cart import cart_to_pdf_bytes


BASE_DIR = Path(__file__).resolve().parent.parent
ORDER_FROM_NAME = "California Earrings"
ORDER_EMAIL_MAX_RETRIES = max(0, int(os.getenv("ORDER_EMAIL_MAX_RETRIES", "0") or "0"))
ORDER_EMAIL_RETRY_DELAY_SECONDS = max(0.0, float(os.getenv("ORDER_EMAIL_RETRY_DELAY_SECONDS", "1") or "1"))
ORDER_EMAIL_REQUEST_TIMEOUT_SECONDS = max(1.0, float(os.getenv("ORDER_EMAIL_REQUEST_TIMEOUT_SECONDS", "8") or "8"))
MAX_ORDER_ITEM_QUANTITY = 999

ORDER_LOG_DIR = BASE_DIR / "logs"
ORDER_DB_PATH = ORDER_LOG_DIR / "orders.db"
ORDER_EVENT_LOG_DIR = ORDER_LOG_DIR / ".logs"
_LEGACY_ORDER_CSV_DIR = ORDER_LOG_DIR / "orders_csv"
ORDER_CSV_DIR = _LEGACY_ORDER_CSV_DIR if _LEGACY_ORDER_CSV_DIR.exists() else ORDER_LOG_DIR / "order_csv"
EMAIL_LOGO_IMAGE_PATH = BASE_DIR / "static" / "assets" / "ce_logo_gold.png"
EMAIL_SIGNATURE_IMAGE_PATH = BASE_DIR / "static" / "assets" / "ce_email_signature.jpg"
_CURRENT_LOG_PATH: Path | None = None


@dataclass(frozen=True)
class EmailSettings:
    sender_email: str
    notify_email: str
    bcc_emails: tuple[str, ...]
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_sender_upn: str = ""


class OrderEmailDeliveryError(RuntimeError):
    def __init__(self, message: str, *, order_id: str, csv_path: Path, csv_text: str) -> None:
        super().__init__(message)
        self.order_id = order_id
        self.csv_path = csv_path
        self.csv_text = csv_text


def _normalized_email(value: str) -> str:
    parsed = parseaddr((value or "").strip())[1].strip()
    if not parsed or "@" not in parsed:
        return ""
    return parsed


def _load_email_settings() -> EmailSettings:
    configured_transport = (os.getenv("EMAIL_TRANSPORT", "graph") or "graph").strip().lower()
    if configured_transport != "graph":
        raise RuntimeError("Only EMAIL_TRANSPORT=graph is supported.")

    smtp_user = _normalized_email(os.getenv("SMTP_USER", ""))
    raw_bcc_emails = os.getenv("ORDER_BCC_EMAILS", "")
    bcc_emails = tuple(
        dict.fromkeys(
            email
            for email in (
                _normalized_email(candidate)
                for candidate in raw_bcc_emails.split(",")
            )
            if email
        )
    )

    graph_tenant_id = (os.getenv("AZURE_TENANT_ID") or os.getenv("TENANT_ID") or "").strip()
    graph_client_id = (os.getenv("AZURE_CLIENT_ID") or os.getenv("CLIENT_ID") or "").strip()
    graph_client_secret = (os.getenv("AZURE_CLIENT_SECRET") or os.getenv("CLIENT_SECRET") or "").strip()
    graph_sender_upn = _normalized_email(os.getenv("GRAPH_SENDER_UPN", "") or smtp_user)

    if not (graph_tenant_id and graph_client_id and graph_client_secret and graph_sender_upn):
        raise RuntimeError(
            "Graph transport requires TENANT_ID/AZURE_TENANT_ID, "
            "CLIENT_ID/AZURE_CLIENT_ID, CLIENT_SECRET/AZURE_CLIENT_SECRET, and GRAPH_SENDER_UPN."
        )

    notify_email = graph_sender_upn
    bcc_emails = tuple(email for email in bcc_emails if email != notify_email)
    return EmailSettings(
        sender_email=graph_sender_upn,
        notify_email=notify_email,
        bcc_emails=bcc_emails,
        graph_tenant_id=graph_tenant_id,
        graph_client_id=graph_client_id,
        graph_client_secret=graph_client_secret,
        graph_sender_upn=graph_sender_upn,
    )


def _normalize_customer(customer: dict[str, Any]) -> dict[str, str]:
    return {
        "name": str(customer.get("name") or "").strip(),
        "company": str(customer.get("company") or "").strip(),
        "phone": str(customer.get("phone") or "").strip(),
        "email": _normalized_email(str(customer.get("email") or "")),
        "city": str(customer.get("city") or "").strip(),
        "state": str(customer.get("state") or "").strip(),
        "country": str(customer.get("country") or "").strip(),
        "notes": str(customer.get("notes") or "").strip(),
    }


def _normalize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or "").strip() or code
        collection = str(item.get("collection") or "").strip()
        item_notes = str(item.get("notes") or item.get("note") or "").strip()
        image = str(item.get("image") or "").strip()

        try:
            quantity = int(item.get("qty", item.get("quantity", 0)) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid quantity for order item {code or '<unknown>'}.") from exc

        if not code:
            raise ValueError("Every order item requires a valid product code.")
        if quantity <= 0 or quantity > MAX_ORDER_ITEM_QUANTITY:
            raise ValueError(f"Invalid quantity for order item {code}.")

        normalized_items.append(
            {
                "code": code,
                "name": name,
                "collection": collection,
                "quantity": quantity,
                "notes": item_notes,
                "image": image,
            }
        )

    if not normalized_items:
        raise ValueError("At least one valid order item is required.")

    return normalized_items


def ensure_storage() -> None:
    ORDER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ORDER_CSV_DIR.mkdir(parents=True, exist_ok=True)
    ORDER_EVENT_LOG_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(ORDER_DB_PATH, timeout=30) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS order_sequence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def next_order_number() -> tuple[int, str]:
    ensure_storage()
    created_at = datetime.now().isoformat(timespec="seconds")

    with sqlite3.connect(ORDER_DB_PATH, timeout=30) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            "INSERT INTO order_sequence (created_at) VALUES (?)",
            (created_at,),
        )
        conn.commit()
        order_num = int(cursor.lastrowid or 0)

    return order_num, f"#{order_num:05d}"


def current_week_log_path() -> Path:
    now = datetime.now()
    week_start = now.date() - timedelta(days=now.weekday())
    return ORDER_EVENT_LOG_DIR / f"email_events_{week_start:%Y%m%d}.log"


def setup_order_logger() -> logging.Logger:
    global _CURRENT_LOG_PATH

    ensure_storage()
    logger = logging.getLogger("order_email_events")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    target_path = current_week_log_path()
    if _CURRENT_LOG_PATH != target_path:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

        handler = logging.FileHandler(target_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)
        _CURRENT_LOG_PATH = target_path

    return logger


def log_event(
    event_type: str,
    order_id: str,
    customer: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    *,
    level: str = "info",
) -> None:
    logger = setup_order_logger()
    payload = {
        "event_type": event_type,
        "order_id": order_id,
        "customer_name": (customer or {}).get("name", ""),
        "company": (customer or {}).get("company", ""),
        "phone": (customer or {}).get("phone", ""),
        "email": (customer or {}).get("email", ""),
        "extra": extra or {},
    }
    message = json.dumps(payload, ensure_ascii=False)

    if level == "error":
        logger.error(message)
    elif level == "warning":
        logger.warning(message)
    else:
        logger.info(message)


def safe_company_name(company: str) -> str:
    sanitized = "".join(
        character
        for character in (company or "Unknown_Company")
        if character.isalnum() or character in {" ", "-", "_"}
    ).strip()
    return (sanitized or "Unknown_Company").replace(" ", "_")


def build_order_csv(order_id: str, customer: dict[str, str], items: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["California Earrings Wholesale Inquiry"])
    writer.writerow(["order_id", order_id])
    writer.writerow(["submitted_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])
    writer.writerow(["customer_name", customer.get("name", "")])
    writer.writerow(["company_name", customer.get("company", "")])
    writer.writerow(["phone", customer.get("phone", "")])
    writer.writerow(["email", customer.get("email", "")])
    writer.writerow(["city", customer.get("city", "")])
    writer.writerow(["state", customer.get("state", "")])
    writer.writerow(["country", customer.get("country", "")])
    writer.writerow(["order_notes", customer.get("notes", "")])
    writer.writerow([])
    writer.writerow(["code", "name", "collection", "quantity", "item_notes"])

    for item in items:
        writer.writerow(
            [
                item.get("code", ""),
                item.get("name", ""),
                item.get("collection", ""),
                item.get("quantity", 0),
                item.get("notes", ""),
            ]
        )

    return buffer.getvalue()


def save_order_csv(order_id: str, customer: dict[str, str], csv_text: str) -> Path:
    ensure_storage()
    timestamp = datetime.now().strftime("%Y%m%d")
    clean_order_id = order_id.replace("#", "")
    csv_path = ORDER_CSV_DIR / f"ce_order_{clean_order_id}_{timestamp}.csv"
    csv_path.write_text(csv_text, encoding="utf-8")
    return csv_path


def build_order_plain_text(order_id: str, customer: dict[str, str], items: list[dict[str, Any]]) -> str:
    total_unique_items = len(items)
    total_quantity = sum(int(item.get("quantity", 0)) for item in items)
    location = ", ".join(part for part in [customer.get("city"), customer.get("state"), customer.get("country")] if part)

    lines = [
        "CALIFORNIA EARRINGS",
        "Wholesaler of 14K Gold Earrings & Piercings",
        "Over 30 Years in Business",
        "",
        "Wholesale inquiry submitted from californiaearrings.com",
        "",
        "ORDER ID",
        order_id,
        "",
        "CUSTOMER DETAILS",
        f"Name: {customer.get('name', '')}",
        f"Company: {customer.get('company', '')}",
        f"Phone: {customer.get('phone', '')}",
        f"Email: {customer.get('email', '') or 'Not provided'}",
        f"Location: {location or 'Not provided'}",
    ]

    if customer.get("notes"):
        lines.append(f"Order notes: {customer['notes']}")

    lines.extend(
        [
            "",
            "ORDER SUMMARY",
            f"Total unique items: {total_unique_items}",
            f"Total quantity: {total_quantity}",
            "",
            "ITEMS",
        ]
    )

    for index, item in enumerate(items, start=1):
        line = (
            f"{index}. {item.get('code', '')} | {item.get('name', '')} | "
            f"{item.get('collection', '')} | Qty: {item.get('quantity', 0)}"
        )
        if item.get("notes"):
            line = f"{line} | Notes: {item['notes']}"
        lines.append(line)

    lines.extend(
        [
            "",
            "CSV attachment included.",
            "",
            "Next step:",
            "Contact customer to confirm availability, pricing, and fulfillment details.",
            "",
            "California Earrings",
            "650 S Hill St Suite 518",
            "Los Angeles, CA 90014",
            "Office: +1 (213) 935-7272",
            "Mobile: +1 (818) 331-9292",
            "californiaearrings.com",
            "Instagram: @california_earrings",
        ]
    )
    return "\n".join(lines)


def build_order_html(
    order_id: str,
    customer: dict[str, str],
    items: list[dict[str, Any]],
    *,
    logo_cid: str | None = None,
    signature_cid: str | None = None,
) -> str:
    total_unique_items = len(items)
    total_quantity = sum(int(item.get("quantity", 0)) for item in items)
    location = ", ".join(part for part in [customer.get("city"), customer.get("state"), customer.get("country")] if part)
    customer_notes = escape(customer.get("notes", ""))

    item_rows: list[str] = []
    for index, item in enumerate(items, start=1):
        item_rows.append(
            """
        <tr>
          <td style="padding:10px;border-bottom:1px solid #333;color:#d7c07a;">{index}</td>
          <td style="padding:10px;border-bottom:1px solid #333;color:#ffffff;font-weight:bold;">{code}</td>
          <td style="padding:10px;border-bottom:1px solid #333;color:#eeeeee;">{name}</td>
          <td style="padding:10px;border-bottom:1px solid #333;color:#cccccc;">{collection}</td>
          <td style="padding:10px;border-bottom:1px solid #333;color:#cccccc;">{notes}</td>
          <td style="padding:10px;border-bottom:1px solid #333;color:#ffffff;text-align:right;font-weight:bold;">{quantity}</td>
        </tr>
        """.format(
                index=index,
                code=escape(str(item.get("code", ""))),
                name=escape(str(item.get("name", ""))),
                collection=escape(str(item.get("collection", ""))),
                notes=escape(str(item.get("notes", ""))) or "-",
                quantity=int(item.get("quantity", 0)),
            )
        )

    if logo_cid:
        brand_html = f"""
            <img src="cid:{logo_cid}" alt="California Earrings" style="max-width:280px;width:100%;height:auto;display:block;">
        """
    else:
        brand_html = """
            <div style="font-size:26px;letter-spacing:1px;color:#d7c07a;font-weight:bold;">California Earrings</div>
        """

    if signature_cid:
        signature_html = f"""
        <div style="padding:18px 32px;border-top:1px solid #333;background:#ffffff;text-align:center;">
          <img src="cid:{signature_cid}" alt="California Earrings" style="max-width:650px;width:100%;height:auto;display:block;margin:0 auto;">
        </div>
        """
    else:
        signature_html = """
        <div style="padding:18px 32px;border-top:1px solid #333;color:#999;font-size:13px;background:#0d0d0d;line-height:1.5;">
          California Earrings<br>
          650 S Hill St Suite 518, Los Angeles, CA 90014<br>
          Office: +1 (213) 935-7272<br>
          Mobile: +1 (818) 331-9292<br>
          californiaearrings.com<br>
          Instagram: @california_earrings
        </div>
        """

    location_value = escape(location) if location else "Not provided"
    order_notes_block = ""
    if customer_notes:
        order_notes_block = f"""
            <tr><td style="padding:6px 0;color:#999;vertical-align:top;">Notes</td><td style="padding:6px 0;color:#fff;">{customer_notes}</td></tr>
        """

    return f"""
    <html>
      <body style="margin:0;padding:0;background:#0d0d0d;color:#eeeeee;font-family:Arial,Helvetica,sans-serif;">
        <div style="max-width:760px;margin:0 auto;background:#111111;border:1px solid #4a3a16;">
          <div style="padding:28px 32px;border-bottom:1px solid #d7c07a;background:#0d0d0d;">
                        {brand_html}
                        <div style="margin-top:6px;color:#c9b36a;font-size:15px;font-weight:bold;text-align:center;">Wholesaler of 14K Gold Earrings &amp; Piercings · Over 30 Years in Business</div>
          </div>

          <div style="padding:28px 32px;">
            <h1 style="margin:0 0 18px;color:#ffffff;font-size:24px;">Wholesale Inquiry {escape(order_id)}</h1>

            <div style="background:#0d0d0d;border:1px solid #333;padding:18px;margin-bottom:22px;">
              <h2 style="margin:0 0 12px;color:#d7c07a;font-size:16px;">Customer Details</h2>
              <table style="width:100%;border-collapse:collapse;font-size:14px;">
                <tr><td style="padding:6px 0;color:#999;">Order ID</td><td style="padding:6px 0;color:#fff;font-weight:bold;">{escape(order_id)}</td></tr>
                <tr><td style="padding:6px 0;color:#999;">Name</td><td style="padding:6px 0;color:#fff;">{escape(customer.get('name', ''))}</td></tr>
                <tr><td style="padding:6px 0;color:#999;">Company</td><td style="padding:6px 0;color:#fff;">{escape(customer.get('company', ''))}</td></tr>
                <tr><td style="padding:6px 0;color:#999;">Phone</td><td style="padding:6px 0;color:#fff;">{escape(customer.get('phone', ''))}</td></tr>
                <tr><td style="padding:6px 0;color:#999;">Email</td><td style="padding:6px 0;color:#fff;">{escape(customer.get('email', '') or 'Not provided')}</td></tr>
                <tr><td style="padding:6px 0;color:#999;">Location</td><td style="padding:6px 0;color:#fff;">{location_value}</td></tr>
                {order_notes_block}
              </table>
            </div>

            <div style="background:#0d0d0d;border:1px solid #333;padding:18px;margin-bottom:22px;">
              <h2 style="margin:0 0 12px;color:#d7c07a;font-size:16px;">Order Summary</h2>
              <p style="margin:0;color:#eeeeee;">Total unique items: <strong>{total_unique_items}</strong></p>
              <p style="margin:6px 0 0;color:#eeeeee;">Total quantity: <strong>{total_quantity}</strong></p>
            </div>

            <table style="width:100%;border-collapse:collapse;font-size:14px;background:#0d0d0d;border:1px solid #333;">
              <thead>
                <tr style="background:#1a1a1a;">
                  <th style="padding:10px;text-align:left;color:#d7c07a;">#</th>
                  <th style="padding:10px;text-align:left;color:#d7c07a;">Code</th>
                  <th style="padding:10px;text-align:left;color:#d7c07a;">Item</th>
                  <th style="padding:10px;text-align:left;color:#d7c07a;">Collection</th>
                  <th style="padding:10px;text-align:left;color:#d7c07a;">Notes</th>
                  <th style="padding:10px;text-align:right;color:#d7c07a;">Qty</th>
                </tr>
              </thead>
              <tbody>{''.join(item_rows)}</tbody>
            </table>

            <div style="margin-top:24px;padding:16px;border-left:3px solid #d7c07a;background:#161616;">
              <p style="margin:0;color:#eeeeee;line-height:1.5;">Next step: contact the customer to confirm availability, pricing, and fulfillment details.</p>
            </div>
          </div>

          {signature_html}
        </div>
      </body>
    </html>
    """


def _guess_image_type(path: Path) -> tuple[str, str]:
    extension = path.suffix.lower()
    return {
        ".jpg": ("image", "jpeg"),
        ".jpeg": ("image", "jpeg"),
        ".png": ("image", "png"),
        ".gif": ("image", "gif"),
        ".webp": ("image", "webp"),
    }.get(extension, ("image", "jpeg"))


def _inline_image_attachments() -> dict[str, tuple[bytes, str, str, str]]:
    inline_images: dict[str, tuple[bytes, str, str, str]] = {}

    if EMAIL_LOGO_IMAGE_PATH.exists():
        logo_cid = make_msgid(domain="californiaearrings.com")[1:-1]
        logo_maintype, logo_subtype = _guess_image_type(EMAIL_LOGO_IMAGE_PATH)
        inline_images["logo"] = (
            EMAIL_LOGO_IMAGE_PATH.read_bytes(),
            logo_maintype,
            logo_subtype,
            logo_cid,
        )

    if EMAIL_SIGNATURE_IMAGE_PATH.exists():
        signature_cid = make_msgid(domain="californiaearrings.com")[1:-1]
        signature_maintype, signature_subtype = _guess_image_type(EMAIL_SIGNATURE_IMAGE_PATH)
        inline_images["signature"] = (
            EMAIL_SIGNATURE_IMAGE_PATH.read_bytes(),
            signature_maintype,
            signature_subtype,
            signature_cid,
        )

    return inline_images


def make_message(
    order_id: str,
    customer: dict[str, str],
    items: list[dict[str, Any]],
    csv_text: str,
    csv_path: Path,
    settings: EmailSettings,
    *,
    fallback: bool,
    base_dir: Path | None = None,
) -> EmailMessage:
    if base_dir is None:
        base_dir = BASE_DIR
    company = customer.get("company") or "Unknown Company"
    subject = (
        f"URGENT: Order Email Retry Failed {order_id} - {company}"
        if fallback
        else f"{company.capitalize()} | Wholesale Inquiry"
    )

    inline_images = _inline_image_attachments()
    logo_cid = inline_images["logo"][3] if "logo" in inline_images else None
    signature_cid = inline_images["signature"][3] if "signature" in inline_images else None

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((ORDER_FROM_NAME, settings.sender_email))

    customer_email = _normalized_email(customer.get("email", ""))
    if customer_email:
        message["To"] = customer_email
        bcc_recipients = [settings.notify_email, *settings.bcc_emails]
    else:
        message["To"] = settings.notify_email
        bcc_recipients = list(settings.bcc_emails)

    deduped_bcc = [
        recipient
        for recipient in dict.fromkeys(recipient for recipient in bcc_recipients if recipient)
        if recipient != message["To"]
    ]
    if deduped_bcc:
        message["Bcc"] = ", ".join(deduped_bcc)

    message.set_content(build_order_plain_text(order_id, customer, items))
    message.add_alternative(
        build_order_html(order_id, customer, items, logo_cid=logo_cid, signature_cid=signature_cid),
        subtype="html",
    )

    html_part = message.get_body(preferencelist=("html",))
    if html_part is not None:
        if "logo" in inline_images:
            logo_bytes, logo_maintype, logo_subtype, logo_cid = inline_images["logo"]
            html_part.add_related(
                logo_bytes,
                maintype=logo_maintype,
                subtype=logo_subtype,
                cid=f"<{logo_cid}>",
                filename=EMAIL_LOGO_IMAGE_PATH.name,
                disposition="inline",
            )

        if "signature" in inline_images:
            signature_bytes, signature_maintype, signature_subtype, signature_cid = inline_images["signature"]
            html_part.add_related(
                signature_bytes,
                maintype=signature_maintype,
                subtype=signature_subtype,
                cid=f"<{signature_cid}>",
                filename=EMAIL_SIGNATURE_IMAGE_PATH.name,
                disposition="inline",
            )

    # Convert email items to PDF order row format (preserving product images)
    pdf_order_rows = [
        {
            "code": str(item.get("code", "")),
            "name": str(item.get("name", "")),
            "quantity": int(item.get("quantity", 0)),
            "notes": str(item.get("notes", "")),
            "image": str(item.get("image", "")),
        }
        for item in items
    ]
    product_images_dir = base_dir / "static" / "product_images"
    pdf_bytes = cart_to_pdf_bytes(pdf_order_rows, product_images_dir)
    pdf_filename = csv_path.name.replace(".csv", ".pdf")

    message.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=pdf_filename,
    )
    message.add_attachment(
        csv_text.encode("utf-8"),
        maintype="text",
        subtype="csv",
        filename=csv_path.name,
    )
    return message


def _fetch_graph_access_token(settings: EmailSettings) -> str:
    token_url = f"https://login.microsoftonline.com/{settings.graph_tenant_id}/oauth2/v2.0/token"
    payload = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": settings.graph_client_id,
            "client_secret": settings.graph_client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }
    ).encode("utf-8")

    request = Request(
        token_url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=ORDER_EMAIL_REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Graph token request failed ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Graph token request failed: {exc.reason}") from exc

    body = json.loads(raw)
    token = str(body.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Graph token response did not include an access_token.")
    return token


def graph_send(message: EmailMessage, settings: EmailSettings) -> None:
    access_token = _fetch_graph_access_token(settings)
    mime_bytes = message.as_bytes(policy=SMTP)
    mime_payload = base64.b64encode(mime_bytes)

    send_url = f"https://graph.microsoft.com/v1.0/users/{quote(settings.graph_sender_upn)}/sendMail"
    request = Request(
        send_url,
        data=mime_payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "text/plain",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=ORDER_EMAIL_REQUEST_TIMEOUT_SECONDS) as response:
            status_code = response.getcode()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Graph sendMail failed ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Graph sendMail failed: {exc.reason}") from exc

    if status_code != 202:
        raise RuntimeError(f"Graph sendMail returned unexpected status: {status_code}")


def send_with_retry(
    message: EmailMessage,
    order_id: str,
    customer: dict[str, str],
    settings: EmailSettings,
    *,
    mode: str,
) -> bool:
    for attempt in range(1, ORDER_EMAIL_MAX_RETRIES + 2):
        try:
            log_event(f"{mode}_attempt", order_id, customer, {"attempt": attempt})
            graph_send(message, settings)
            log_event(f"{mode}_success", order_id, customer, {"attempt": attempt})
            return True
        except Exception as exc:
            log_event(
                f"{mode}_failure",
                order_id,
                customer,
                {"attempt": attempt, "error": repr(exc)},
                level="error",
            )
            if attempt <= ORDER_EMAIL_MAX_RETRIES:
                time.sleep(ORDER_EMAIL_RETRY_DELAY_SECONDS)

    return False


def send_order_email(customer: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_storage()
    normalized_customer = _normalize_customer(customer)
    normalized_items = _normalize_items(items)
    _, order_id = next_order_number()

    csv_text = build_order_csv(order_id, normalized_customer, normalized_items)
    csv_path = save_order_csv(order_id, normalized_customer, csv_text)
    log_event(
        "order_csv_saved",
        order_id,
        normalized_customer,
        {"csv_path": str(csv_path), "item_count": len(normalized_items)},
    )

    try:
        settings = _load_email_settings()
    except RuntimeError as exc:
        log_event(
            "order_email_configuration_error",
            order_id,
            normalized_customer,
            {"error": str(exc)},
            level="error",
        )
        raise OrderEmailDeliveryError(
            str(exc),
            order_id=order_id,
            csv_path=csv_path,
            csv_text=csv_text,
        ) from exc

    normal_message = make_message(
        order_id,
        normalized_customer,
        normalized_items,
        csv_text,
        csv_path,
        settings,
        fallback=False,
    )
    if send_with_retry(normal_message, order_id, normalized_customer, settings, mode="order_email"):
        return {
            "ok": True,
            "order_id": order_id,
            "csv_path": str(csv_path),
            "csv_text": csv_text,
            "csv_filename": csv_path.name,
            "fallback_used": False,
        }

    log_event(
        "order_email_exhausted_retries",
        order_id,
        normalized_customer,
        {"csv_path": str(csv_path)},
        level="error",
    )

    fallback_message = make_message(
        order_id,
        normalized_customer,
        normalized_items,
        csv_text,
        csv_path,
        settings,
        fallback=True,
    )
    if send_with_retry(fallback_message, order_id, normalized_customer, settings, mode="fallback_email"):
        return {
            "ok": True,
            "order_id": order_id,
            "csv_path": str(csv_path),
            "csv_text": csv_text,
            "csv_filename": csv_path.name,
            "fallback_used": True,
        }

    log_event(
        "fallback_email_failed",
        order_id,
        normalized_customer,
        {"csv_path": str(csv_path)},
        level="error",
    )
    raise OrderEmailDeliveryError(
        f"Order email and fallback email both failed for order_id={order_id}",
        order_id=order_id,
        csv_path=csv_path,
        csv_text=csv_text,
    )
