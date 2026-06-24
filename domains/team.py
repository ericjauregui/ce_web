from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from domains.file_cache import load_json_cached


def load_team(team_path: Path) -> dict[str, Any]:
    if team_path.exists():
        return load_json_cached(team_path, {})
    return {
        "headline": "Meet the Team",
        "company": "California Earrings",
        "whatsapp_intro": "Hi {name}, I found your contact on {company}.",
        "members": [],
    }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return slug or "member"


def _name_parts_for_slug(name: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (name or "").strip().lower())


def _member_slug_base(name: str) -> tuple[str, str]:
    parts = _name_parts_for_slug(name)
    if not parts:
        return "member", ""
    first = _slugify(parts[0])
    last_initial = parts[-1][0] if len(parts) > 1 and parts[-1] else ""
    return first, last_initial


def build_team_members(team: dict[str, Any]) -> list[dict[str, Any]]:
    raw_members = team.get("members") or []
    if not isinstance(raw_members, list):
        raw_members = []

    members: list[dict[str, Any]] = []
    seen_slugs: dict[str, int] = {}
    member_names: list[str] = []
    first_name_counts: dict[str, int] = {}
    company = (team.get("company") or "California Earrings").strip() or "California Earrings"
    whatsapp_intro_template = team.get("whatsapp_intro") or "Hi {name}, I found your contact on {company}."

    for raw in raw_members:
        source = raw if isinstance(raw, dict) else {}
        name = (source.get("name") or "Team Member").strip() or "Team Member"
        member_names.append(name)
        first_slug, _ = _member_slug_base(name)
        first_name_counts[first_slug] = first_name_counts.get(first_slug, 0) + 1

    for raw, name in zip(raw_members, member_names, strict=False):
        source = raw if isinstance(raw, dict) else {}
        title = (source.get("title") or "").strip()
        bio = (source.get("bio") or "").strip()
        photo = (source.get("photo") or "").strip() or None
        phone = (source.get("phone") or "").strip()
        email = (source.get("email") or "").strip()

        first_slug, last_initial = _member_slug_base(name)
        if first_name_counts.get(first_slug, 0) > 1:
            suffix = last_initial or "x"
            candidate_slug = f"{first_slug}-{suffix}"
        else:
            candidate_slug = first_slug

        seen_slugs[candidate_slug] = seen_slugs.get(candidate_slug, 0) + 1
        slug = candidate_slug if seen_slugs[candidate_slug] == 1 else f"{candidate_slug}-{seen_slugs[candidate_slug]}"

        phone_digits = re.sub(r"\D+", "", phone)
        if phone_digits.startswith("00"):
            phone_digits = phone_digits[2:]

        whatsapp_url = ""
        if phone_digits:
            member_intro = source.get("whatsapp_intro") or whatsapp_intro_template
            try:
                intro = str(member_intro).format(name=name, company=company)
            except Exception:
                intro = f"Hi {name}, I found your contact on {company}."
            text = quote_plus(intro)
            whatsapp_url = f"https://wa.me/{phone_digits}?text={text}"

        members.append(
            {
                "name": name,
                "title": title,
                "bio": bio,
                "photo": photo,
                "phone": phone,
                "email": email,
                "slug": slug,
                "phone_digits": phone_digits,
                "whatsapp_url": whatsapp_url,
                "call_url": f"tel:{phone_digits}" if phone_digits else "",
            }
        )

    return members


def get_team_member_by_slug(member_slug: str, team: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    members = build_team_members(team)
    member = next((item for item in members if item.get("slug") == member_slug), None)
    return members, member


def vcard_escape(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _split_vcard_name(name: str) -> tuple[str, str]:
    parts = [part for part in (name or "").strip().split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def _fold_vcard_line(line: str, limit: int = 75) -> str:
    if len(line) <= limit:
        return line

    chunks = [line[:limit]]
    remaining = line[limit:]
    while remaining:
        chunks.append(f" {remaining[: limit - 1]}")
        remaining = remaining[limit - 1:]
    return "\n".join(chunks)


def _normalize_vcard_photo_type(photo_filename: str | None) -> str | None:
    suffix = Path(photo_filename or "").suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "JPEG"
    if suffix == ".png":
        return "PNG"
    if suffix == ".gif":
        return "GIF"
    return None


def build_member_vcard(
    member: dict[str, Any],
    team: dict[str, Any],
    *,
    photo_bytes: bytes | None = None,
    photo_type: str | None = None,
) -> str:
    company = (team.get("company") or "California Earrings").strip() or "California Earrings"
    full_name = str(member.get("name") or "").strip()
    family_name, given_name = _split_vcard_name(full_name)
    title = str(member.get("title") or "").strip()
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{vcard_escape(full_name)}",
        f"N:{vcard_escape(family_name)};{vcard_escape(given_name)};;;",
        f"ORG:{vcard_escape(company)}",
    ]

    if title:
        lines.append(f"TITLE:{vcard_escape(title)}")

    phone_digits = member.get("phone_digits") or ""
    if phone_digits:
        lines.append(f"TEL;TYPE=CELL:{vcard_escape(phone_digits)}")

    office_phone_raw = str(team.get("office_phone") or "+1-213-935-7272").strip()
    office_phone_digits = re.sub(r"\D+", "", office_phone_raw)
    if office_phone_digits and office_phone_digits != phone_digits:
        lines.append(f"TEL;TYPE=WORK,VOICE:{vcard_escape(office_phone_digits)}")

    email = member.get("email") or ""
    if email:
        lines.append(f"EMAIL;TYPE=INTERNET:{vcard_escape(email)}")

    website = str(team.get("website") or "https://californiaearrings.com").strip()
    if website:
        lines.append(f"URL:{vcard_escape(website)}")

    street = str(team.get("street_address") or "650 S Hill St Suite 518").strip()
    city = str(team.get("address_locality") or "Los Angeles").strip()
    region = str(team.get("address_region") or "CA").strip()
    postal = str(team.get("postal_code") or "90014").strip()
    country = str(team.get("address_country") or "US").strip()
    if street or city or region or postal or country:
        lines.append(
            "ADR;TYPE=WORK:;;"
            f"{vcard_escape(street)};"
            f"{vcard_escape(city)};"
            f"{vcard_escape(region)};"
            f"{vcard_escape(postal)};"
            f"{vcard_escape(country)}"
        )

    if photo_bytes and photo_type:
        encoded_photo = base64.b64encode(photo_bytes).decode("ascii")
        lines.append(_fold_vcard_line(f"PHOTO;ENCODING=b;TYPE={photo_type}:{encoded_photo}"))

    lines.extend(["END:VCARD", ""])
    return "\n".join(lines)


def slugify(value: str) -> str:
    return _slugify(value)
