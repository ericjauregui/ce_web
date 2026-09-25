# Permanent trade-show QR destination

Print `https://californiaearrings.com/connect` in the QR. The printed URL stays the same for every show. The page has no menu entry and no query parameter is required.

`catalog/trade_shows.json` is the one source for event names, booth numbers, dates, and venue time zones. `/connect` selects an event when its local date is between `start_date` and `end_date`, inclusive. Before and after those dates it shows the generic page. If event dates overlap, the event selected by `active_event` wins; otherwise the most recently started show wins. `active_event` continues to control the main `/trade-shows` page independently.

For a temporary testing or emergency override, set `connect_event_override` to an event key such as `"jis-fall-2026"`. Set it back to `null` to restore date detection. Leaving an override set intentionally bypasses automatic expiration.

The Save Our Contact button downloads Giancarlo Jauregui's existing contact details with the company phone, business email, website, social links, WhatsApp URL, and a note naming the current show and booth. It omits the show note when no event is active.

The existing Cloudflare Web Analytics beacon remains on the page for page performance and visits. A small first-party endpoint separately increments aggregate `connect_event_counts` rows for `visit`, `whatsapp`, `save_contact`, `instagram`, `tiktok`, and `shop`. Rows contain the date, show key/name, booth, action, and count. They do not contain IP addresses, device identifiers, or contact details. The permanent `/connect` URL needs no query parameters.

Run the normal database migration before deploying the app. For a show summary, query the configured PostgreSQL database privately:

```sql
SELECT trade_show_name, booth, action, SUM(count) AS total
FROM connect_event_counts
GROUP BY trade_show_name, booth, action
ORDER BY trade_show_name, booth, action;
```

`visit` counts loaded browser pages, including repeat visits. A click records intent to open an action; it does not prove a WhatsApp conversation, successful contact import, or completed wholesale order. Analytics failures do not block any action.
