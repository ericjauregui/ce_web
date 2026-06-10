# California Earrings Order Email Workflow Implementation

## Objective

Implement a production-safe order/inquiry email workflow for the California Earrings website.

When a customer submits the inquiry cart, the Flask backend should:

1. Receive customer details and cart items.
2. Validate submitted product codes and quantities against the product catalog.
3. Generate a professional internal order email.
4. Generate a CSV attachment.
5. Save a copy of the generated CSV to `logs/orders_csvs/`.
6. Log every email attempt, success, failure, retry, and fallback event to a weekly log file in `logs/.logs/`.
7. Send the order email from `orders@californiaearrings.com`.
8. Send the primary email to `orders@californiaearrings.com`.
9. BCC the internal team.
10. Retry failed sends.
11. If the normal order email fails after retries, attempt a fallback alert email to the same internal recipients with the order details inline.
12. Return success to the frontend only when the normal order email or fallback alert email has been sent.

---

## Required Render Environment Variables

Only these email-related environment variables are required for this workflow:

```env
SMTP_USER=orders@californiaearrings.com
SMTP_PASS=<MICROSOFT_365_MAILBOX_PASSWORD>
ORDER_BCC_EMAILS=californiaearrings@gmail.com,miguel@californiaearrings.com,giancarlo@californiaearrings.com,aricaliforniaearrings@gmail.com
```

Notes:

- `SMTP_USER` is the GoDaddy Microsoft 365 mailbox.
- `SMTP_PASS` is the mailbox password.
- `ORDER_BCC_EMAILS` is comma-separated with no spaces.
- Do not commit these values to GitHub.
- `SITE_BASE_URL` is already configured separately in Render and does not need to be part of this implementation.

---

## Hardcoded Email Constants

Keep these values inside `utils/emailer.py`, not in Render:

```python
SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587

ORDER_FROM_NAME = "California Earrings"
ORDER_NOTIFY_EMAIL = SMTP_USER

ORDER_LOG_DIR = Path("logs")
ORDER_CSV_DIR = Path("logs/order_csv")
ORDER_EVENT_LOG_DIR = Path("logs/.logs")

ORDER_EMAIL_MAX_RETRIES = 2
ORDER_EMAIL_RETRY_DELAY_SECONDS = 3
```

Why:

- Microsoft 365 SMTP host/port are fixed.
- Sender display name is fixed branding.
- Primary recipient should always be the sender mailbox.
- Logging paths are implementation details.
- Retry count/delay are implementation details.
- Only the password and BCC list need to be configurable in Render.

---

## SMTP Settings

Because this mailbox is GoDaddy Microsoft 365 Email Essentials, use Microsoft 365 SMTP:

```text
SMTP Host: smtp.office365.com
SMTP Port: 587
Encryption: STARTTLS
Username: orders@californiaearrings.com
Password: mailbox password
```

Do not use the old GoDaddy Workspace host:

```text
smtpout.secureserver.net
```

---

## Recommended Email Routing

### From

```text
California Earrings <orders@californiaearrings.com>
```

### To

```text
orders@californiaearrings.com
```

### BCC

```text
californiaearrings@gmail.com
miguel@californiaearrings.com
giancarlo@californiaearrings.com
aricaliforniaearrings@gmail.com
```

Use **BCC**, not CC.

Why:

- Keeps the internal recipient list private.
- Avoids reply-all clutter.
- Looks cleaner and more professional.
- Keeps `orders@californiaearrings.com` as the main order inbox.

---

## Important Hosting Note About Render Logs

Render's filesystem is ephemeral. Files written to `logs/` can disappear after:

- redeploys
- service restarts
- instance replacement
- scaling events

The `logs/` approach is useful for short-term debugging and near-term visibility, but it is not durable long-term storage.

For permanent order history later, use one of:

- Postgres
- Google Sheets API
- Cloudflare R2 / S3
- Airtable
- CRM
- dedicated email archive mailbox

For now, saving CSVs locally plus emailing them is acceptable.

---

## Recommended File Structure

Add:

```text
utils/
└── emailer.py

logs/
├── order_csv/
└── .logs/
```

Add `.gitkeep` files so empty folders stay in Git:

```text
logs/order_csv/.gitkeep
logs/.logs/.gitkeep
```

Add to `.gitignore`:

```gitignore
.env
logs/order_csv/*.csv
logs/.logs/*.log
```

---

## Professional Internal Order Email Template

The email should look polished and align with the black/gold wholesale jewelry theme.

### Subject

```text
Order - <Company Name>
```

### Plain Text Body

```text
CALIFORNIA EARRINGS
Wholesale 10K / 14K Gold Earrings & Piercings

New order submitted from californiaearrings.com

CUSTOMER DETAILS
Name: <customer name>
Company: <company>
Phone: <phone>
Email: <email if provided>

ORDER SUMMARY
Total unique items: <n>
Total quantity: <sum qty>

ITEMS
1. 101SB | Micro 4-Prong CZ Stud | Studs | Qty: 12
2. 110PB | Round CZ Pushback Stud | Studs | Qty: 6
3. 1557MSB | Heart CZ Stud | Hearts | Qty: 3

CSV attachment included.

Next step:
Reply directly or contact the customer by phone to confirm availability, pricing, and fulfillment details.

California Earrings
Los Angeles Jewelry District
Wholesale Only
https://californiaearrings.com
```

### HTML Email Design Guidance

Use inline styles only:

- dark/black background
- gold accent headings
- white/gray body text
- bordered customer details box
- item table
- clear next-step section
- CSV attachment included

Do not rely on external CSS files for email.

---

## Complete Email Helper Implementation

Create `utils/emailer.py`:

```python
import csv
import io
import json
import logging
import os
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path


SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587

SMTP_USER = os.environ["SMTP_USER"]
SMTP_PASS = os.environ["SMTP_PASS"]

ORDER_FROM_NAME = "California Earrings"
ORDER_NOTIFY_EMAIL = SMTP_USER

ORDER_BCC_EMAILS = [
    email.strip()
    for email in os.getenv("ORDER_BCC_EMAILS", "").split(",")
    if email.strip()
]

ORDER_LOG_DIR = Path("logs")
ORDER_CSV_DIR = Path("logs/order_csv")
ORDER_EVENT_LOG_DIR = Path("logs/.logs")

ORDER_EMAIL_MAX_RETRIES = 2
ORDER_EMAIL_RETRY_DELAY_SECONDS = 3


def ensure_log_dirs():
    ORDER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ORDER_CSV_DIR.mkdir(parents=True, exist_ok=True)
    ORDER_EVENT_LOG_DIR.mkdir(parents=True, exist_ok=True)


def current_week_log_path():
    now = datetime.now()
    year, week, _ = now.isocalendar()
    return ORDER_EVENT_LOG_DIR / f"email_events_{year}_week_{week:02d}.log"


def setup_order_logger():
    ensure_log_dirs()

    logger = logging.getLogger("order_email_events")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    handler = logging.FileHandler(current_week_log_path(), encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def log_event(event_type, order_id, customer=None, extra=None, level="info"):
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


def make_order_id(customer):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    company = customer.get("company") or "unknown_company"
    safe_company = "".join(
        c for c in company if c.isalnum() or c in (" ", "-", "_")
    ).strip().replace(" ", "_")
    return f"{timestamp}_{safe_company}"


def build_order_csv(customer, items):
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["California Earrings Wholesale Inquiry"])
    writer.writerow([])
    writer.writerow(["customer_name", customer.get("name", "")])
    writer.writerow(["company_name", customer.get("company", "")])
    writer.writerow(["phone", customer.get("phone", "")])
    writer.writerow(["email", customer.get("email", "")])
    writer.writerow([])
    writer.writerow(["code", "name", "collection", "quantity"])

    for item in items:
        writer.writerow([
            item.get("code", ""),
            item.get("name", ""),
            item.get("collection", ""),
            item.get("qty", item.get("quantity", "")),
        ])

    return buffer.getvalue()


def save_order_csv(order_id, csv_text):
    ensure_log_dirs()
    csv_path = ORDER_CSV_DIR / f"order_{order_id}.csv"
    csv_path.write_text(csv_text, encoding="utf-8")
    return csv_path


def build_order_plain_text(customer, items):
    total_unique_items = len(items)
    total_quantity = sum(
        int(item.get("qty", item.get("quantity", 0)))
        for item in items
    )

    lines = [
        "CALIFORNIA EARRINGS",
        "Wholesale 10K / 14K Gold Earrings & Piercings",
        "",
        "New wholesale inquiry submitted from californiaearrings.com",
        "",
        "CUSTOMER DETAILS",
        f"Name: {customer.get('name', '')}",
        f"Company: {customer.get('company', '')}",
        f"Phone: {customer.get('phone', '')}",
        f"Email: {customer.get('email', '')}",
        "",
        "ORDER SUMMARY",
        f"Total unique items: {total_unique_items}",
        f"Total quantity: {total_quantity}",
        "",
        "ITEMS",
    ]

    for idx, item in enumerate(items, start=1):
        qty = item.get("qty", item.get("quantity", ""))
        code = item.get("code", "")
        name = item.get("name", "")
        collection = item.get("collection", "")
        lines.append(f"{idx}. {code} | {name} | {collection} | Qty: {qty}")

    lines.extend([
        "",
        "CSV attachment included.",
        "",
        "Next step:",
        "Reply directly or contact the customer by phone to confirm availability, pricing, and fulfillment details.",
        "",
        "California Earrings",
        "Los Angeles Jewelry District",
        "Wholesale Only",
        "https://californiaearrings.com",
    ])

    return "\n".join(lines)


def build_order_html(customer, items):
    total_unique_items = len(items)
    total_quantity = sum(
        int(item.get("qty", item.get("quantity", 0)))
        for item in items
    )

    item_rows = ""
    for idx, item in enumerate(items, start=1):
        item_rows += f'''
        <tr>
          <td style="padding:10px;border-bottom:1px solid #333;color:#d7c07a;">{idx}</td>
          <td style="padding:10px;border-bottom:1px solid #333;color:#ffffff;font-weight:bold;">{item.get("code", "")}</td>
          <td style="padding:10px;border-bottom:1px solid #333;color:#eeeeee;">{item.get("name", "")}</td>
          <td style="padding:10px;border-bottom:1px solid #333;color:#cccccc;">{item.get("collection", "")}</td>
          <td style="padding:10px;border-bottom:1px solid #333;color:#ffffff;text-align:right;font-weight:bold;">{item.get("qty", item.get("quantity", ""))}</td>
        </tr>
        '''

    return f'''
    <html>
      <body style="margin:0;padding:0;background:#0d0d0d;color:#eeeeee;font-family:Arial,Helvetica,sans-serif;">
        <div style="max-width:760px;margin:0 auto;background:#111111;border:1px solid #4a3a16;">
          <div style="padding:28px 32px;border-bottom:1px solid #d7c07a;background:#0d0d0d;">
            <div style="font-size:26px;letter-spacing:1px;color:#d7c07a;font-weight:bold;">
              California Earrings
            </div>
            <div style="margin-top:6px;color:#c9b36a;font-size:15px;">
              Wholesale 10K / 14K Gold Earrings &amp; Piercings
            </div>
          </div>

          <div style="padding:28px 32px;">
            <h1 style="margin:0 0 18px;color:#ffffff;font-size:24px;">New Wholesale Inquiry</h1>

            <p style="margin:0 0 22px;color:#cccccc;font-size:15px;line-height:1.5;">
              A customer submitted an inquiry from californiaearrings.com. The CSV attachment is included for easy order handling.
            </p>

            <div style="background:#0d0d0d;border:1px solid #333;padding:18px;margin-bottom:22px;">
              <h2 style="margin:0 0 12px;color:#d7c07a;font-size:16px;">Customer Details</h2>
              <table style="width:100%;border-collapse:collapse;font-size:14px;">
                <tr><td style="padding:6px 0;color:#999;">Name</td><td style="padding:6px 0;color:#fff;">{customer.get("name", "")}</td></tr>
                <tr><td style="padding:6px 0;color:#999;">Company</td><td style="padding:6px 0;color:#fff;">{customer.get("company", "")}</td></tr>
                <tr><td style="padding:6px 0;color:#999;">Phone</td><td style="padding:6px 0;color:#fff;">{customer.get("phone", "")}</td></tr>
                <tr><td style="padding:6px 0;color:#999;">Email</td><td style="padding:6px 0;color:#fff;">{customer.get("email", "")}</td></tr>
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
                  <th style="padding:10px;text-align:right;color:#d7c07a;">Qty</th>
                </tr>
              </thead>
              <tbody>{item_rows}</tbody>
            </table>

            <div style="margin-top:24px;padding:16px;border-left:3px solid #d7c07a;background:#161616;">
              <p style="margin:0;color:#eeeeee;line-height:1.5;">
                Next step: contact the customer to confirm pricing, availability, and fulfillment details.
              </p>
            </div>
          </div>

          <div style="padding:18px 32px;border-top:1px solid #333;color:#999;font-size:13px;background:#0d0d0d;">
            California Earrings · Los Angeles Jewelry District · Wholesale Only<br>
            https://californiaearrings.com
          </div>
        </div>
      </body>
    </html>
    '''


def make_message(customer, items, csv_text, csv_path=None, fallback=False):
    company = customer.get("company") or "Unknown Company"

    subject = (
        f"URGENT: Order Email Retry Failed - {company}"
        if fallback
        else f"New Wholesale Inquiry - {company}"
    )

    plain_text = build_order_plain_text(customer, items)
    html = build_order_html(customer, items)

    if fallback:
        plain_text = (
            "The normal order email failed after retry. "
            "This fallback alert contains the same order details.\n\n"
            + plain_text
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((ORDER_FROM_NAME, SMTP_USER))
    msg["To"] = ORDER_NOTIFY_EMAIL

    if ORDER_BCC_EMAILS:
        msg["Bcc"] = ", ".join(ORDER_BCC_EMAILS)

    msg.set_content(plain_text)
    msg.add_alternative(html, subtype="html")

    filename = csv_path.name if csv_path else "california_earrings_order.csv"
    msg.add_attachment(
        csv_text.encode("utf-8"),
        maintype="text",
        subtype="csv",
        filename=filename,
    )

    return msg


def smtp_send(msg):
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)


def send_with_retry(msg, order_id, customer, mode):
    for attempt in range(1, ORDER_EMAIL_MAX_RETRIES + 2):
        try:
            log_event(
                event_type=f"{mode}_attempt",
                order_id=order_id,
                customer=customer,
                extra={"attempt": attempt},
            )

            smtp_send(msg)

            log_event(
                event_type=f"{mode}_success",
                order_id=order_id,
                customer=customer,
                extra={"attempt": attempt},
            )
            return True

        except Exception as exc:
            log_event(
                event_type=f"{mode}_failure",
                order_id=order_id,
                customer=customer,
                extra={"attempt": attempt, "error": repr(exc)},
                level="error",
            )

            if attempt <= ORDER_EMAIL_MAX_RETRIES:
                time.sleep(ORDER_EMAIL_RETRY_DELAY_SECONDS)

    return False


def send_order_email(customer, items):
    if not SMTP_USER or not SMTP_PASS:
        raise RuntimeError("SMTP_USER and SMTP_PASS must be configured.")

    ensure_log_dirs()

    order_id = make_order_id(customer)
    csv_text = build_order_csv(customer, items)
    csv_path = save_order_csv(order_id, csv_text)

    log_event(
        event_type="order_csv_saved",
        order_id=order_id,
        customer=customer,
        extra={"csv_path": str(csv_path), "item_count": len(items)},
    )

    normal_msg = make_message(
        customer=customer,
        items=items,
        csv_text=csv_text,
        csv_path=csv_path,
        fallback=False,
    )

    if send_with_retry(normal_msg, order_id, customer, mode="order_email"):
        return {
            "ok": True,
            "order_id": order_id,
            "csv_path": str(csv_path),
            "fallback_used": False,
        }

    log_event(
        event_type="order_email_exhausted_retries",
        order_id=order_id,
        customer=customer,
        level="error",
    )

    fallback_msg = make_message(
        customer=customer,
        items=items,
        csv_text=csv_text,
        csv_path=csv_path,
        fallback=True,
    )

    if send_with_retry(fallback_msg, order_id, customer, mode="fallback_email"):
        return {
            "ok": True,
            "order_id": order_id,
            "csv_path": str(csv_path),
            "fallback_used": True,
        }

    log_event(
        event_type="fallback_email_failed",
        order_id=order_id,
        customer=customer,
        level="error",
    )

    raise RuntimeError(
        f"Order email and fallback email both failed for order_id={order_id}"
    )
```

---

## Cart Validation Recommendation

Before sending the email, validate submitted cart items against the real product catalog.

Recommended behavior:

- Normalize product codes to uppercase.
- Reject any product code not in `products.json`.
- Convert quantity to integer.
- Reject empty, zero, negative, or unrealistic quantities.
- Use catalog values for product name and collection instead of trusting frontend-submitted values.

Example:

```python
def validate_cart_items(items, products_by_code):
    cleaned = []

    for item in items:
        code = str(item.get("code", "")).strip().upper()

        if code not in products_by_code:
            raise ValueError(f"Invalid product code: {code}")

        try:
            qty = int(item.get("qty", item.get("quantity", 0)))
        except ValueError:
            raise ValueError(f"Invalid quantity for {code}")

        if qty <= 0:
            raise ValueError(f"Quantity must be positive for {code}")

        if qty > 9999:
            raise ValueError(f"Quantity is too high for {code}")

        product = products_by_code[code]

        cleaned.append({
            "code": code,
            "name": product.get("name", ""),
            "collection": product.get("collection", ""),
            "qty": qty,
        })

    return cleaned
```

---

## Flask Route Integration

In the existing checkout route, call:

```python
result = send_order_email(customer, items)
```

Return the `order_id` for debugging:

```python
return jsonify({
    "ok": True,
    "message": "Inquiry submitted successfully.",
    "order_id": result["order_id"],
    "fallback_used": result["fallback_used"],
})
```

If both normal and fallback emails fail, return:

```python
return jsonify({
    "ok": False,
    "error": "Order could not be submitted. Please contact us directly."
}), 500
```

Do not expose SMTP details or stack traces to customers.

---

## Frontend Behavior

Only clear the cart after backend returns:

```json
{ "ok": true }
```

If backend returns an error:

- keep cart intact
- show an error message
- tell customer to call or WhatsApp
- allow retry

---

## Testing Checklist

### Render Env Vars

Confirm these exist in Render:

```text
SMTP_USER
SMTP_PASS
ORDER_BCC_EMAILS
```

### Folder Creation

Confirm these folders exist after first test order:

```text
logs/order_csv/
logs/.logs/
```

### CSV Logging

Confirm a file appears like:

```text
logs/order_csv/order_20260610_153200_ABC_Jewelers.csv
```

### Weekly Email Event Log

Confirm a file appears like:

```text
logs/.logs/email_events_2026_week_24.log
```

### Email Events

The log should contain JSON lines for:

```text
order_csv_saved
order_email_attempt
order_email_success
order_email_failure
order_email_exhausted_retries
fallback_email_attempt
fallback_email_success
fallback_email_failed
```

### Email Validation

Submit a test inquiry and confirm:

- `orders@californiaearrings.com` receives the email.
- All BCC recipients receive the email.
- Subject includes company name.
- Email body has customer details inline.
- Email body has item table.
- CSV attachment opens correctly.
- CSV file is saved under `logs/order_csv/`.
- Event log captures success.

### Failure Testing

Temporarily set a wrong SMTP password in local environment only.

Confirm:

- normal send fails
- retries happen
- failures are logged
- fallback email is attempted
- customer cart is not cleared if both normal and fallback fail

Do not intentionally test bad credentials in production during business hours.

---

## Future Improvements

Recommended later:

- Store orders in Postgres or Google Sheets.
- Send customer confirmation emails.
- Add admin dashboard for inquiries.
- Add CAPTCHA or rate limiting.
- Move email sending to a queue if inquiry volume grows.
- Store CSVs in S3 / Cloudflare R2 for durable archives.
