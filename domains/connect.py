from __future__ import annotations

import re
from json import JSONDecodeError
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from domains.file_cache import load_json_cached
from domains.team import _fold_vcard_line, build_member_vcard, vcard_escape


def _connect_config(trade_shows_path: Path) -> dict[str, Any]:
    try:
        raw = load_json_cached(trade_shows_path, {})
    except (OSError, JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _event_details(events: dict[str, Any], key: str) -> dict[str, str]:
    event = events.get(key)
    if not isinstance(event, dict):
        return {}
    name = str(event.get("connect_name") or event.get("name") or "").strip()
    if not name:
        return {}

    booth = str(event.get("booth") or "").strip()
    if "coming soon" in booth.lower():
        booth = ""
    booth = re.sub(r"\bBooth\s*#\s*(?=\w)", "Booth ", booth, flags=re.IGNORECASE)
    return {"key": key, "name": name, "booth": booth}


def connect_event_by_key(trade_shows_path: Path, key: str) -> dict[str, str] | None:
    if not key:
        return {}
    events = _connect_config(trade_shows_path).get("events")
    if not isinstance(events, dict):
        return None
    details = _event_details(events, key)
    return details or None


def load_connect_event(trade_shows_path: Path, *, now: datetime | None = None) -> dict[str, str]:
    """Select one event on its local show dates, or use an explicit override."""
    raw = _connect_config(trade_shows_path)

    events = raw.get("events")
    if not isinstance(events, dict):
        return {}

    override = raw.get("connect_event_override")
    if isinstance(override, str) and override:
        selected_key = override
    else:
        now = now or datetime.now(timezone.utc)
        matching = []
        for key, candidate in events.items():
            if not isinstance(candidate, dict):
                continue
            try:
                start = date.fromisoformat(candidate["start_date"])
                end = date.fromisoformat(candidate["end_date"])
                event_today = now.astimezone(ZoneInfo(candidate.get("time_zone") or "UTC")).date()
            except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
                continue
            if start <= event_today <= end:
                matching.append((start, str(key)))
        active_key = raw.get("active_event")
        selected_key = (
            active_key if isinstance(active_key, str) and any(key == active_key for _, key in matching)
            else max(matching)[1] if matching else ""
        )

    return _event_details(events, selected_key)


def connect_whatsapp_url(event: dict[str, Any], phone_digits: str) -> str:
    if event:
        where = event["name"]
        if event.get("booth"):
            where += f", {event['booth']}"
        message = f"Hi! I met California Earrings at {where} and wanted to stay connected."
    else:
        message = "Hi! I met California Earrings at a trade show and wanted to stay connected."
    return f"https://wa.me/{phone_digits}?text={quote_plus(message)}"


def build_connect_vcard(
    member: dict[str, Any],
    team: dict[str, Any],
    social: dict[str, Any],
    event: dict[str, str],
    *,
    photo_bytes: bytes | None = None,
    photo_type: str | None = None,
) -> str:
    """Extend Giancarlo's existing card with business and show contact details."""
    vcard = build_member_vcard(member, team, photo_bytes=photo_bytes, photo_type=photo_type)
    extra = ["EMAIL;TYPE=WORK:californiaearrings@gmail.com"]
    for kind, url in (
        ("Instagram", (social.get("instagram") or {}).get("profile_url")),
        ("TikTok", (social.get("tiktok") or {}).get("profile_url")),
        ("WhatsApp", f"https://wa.me/{member['phone_digits']}"),
    ):
        if url:
            extra.append(f"URL;TYPE={kind}:{vcard_escape(str(url))}")
    if event:
        location = event["name"]
        if event.get("booth"):
            location += f" — {event['booth']}"
        extra.append(f"NOTE:{vcard_escape('Met at ' + location)}")
    return vcard.replace(
        "END:VCARD\r\n",
        "\r\n".join(_fold_vcard_line(line) for line in extra) + "\r\nEND:VCARD\r\n",
        1,
    )
