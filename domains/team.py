from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote_plus

from domains.file_cache import load_json_cached


_qr_assets_lock = Lock()
_QR_GENERATOR_VERSION = "4"


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
    office_phone = str(team.get("office_phone") or "+1 (213) 935-7272").strip()
    office_phone_digits = re.sub(r"\D+", "", office_phone)
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
                "photo_scale": source.get("photo_scale") or 1,
                "photo_position": str(source.get("photo_position") or "50% 50%"),
                "social_image": str(source.get("social_image") or "assets/social_preview.png"),
                "phone": phone,
                "office_phone": office_phone,
                "office_call_url": f"tel:+{office_phone_digits}" if office_phone_digits else "",
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
    return "\r\n".join(lines)


def _render_vcard_qr_svg(vcard_text: str, logo_bytes: bytes | None = None) -> str:
    """Render a branded, scanner-friendly QR containing the vCard itself."""
    from reportlab.graphics import renderSVG
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors

    qr_widget = QrCodeWidget(vcard_text)
    qr_widget.barLevel = "M"
    qr_widget.barFillColor = colors.white
    qr_widget.barStrokeColor = colors.white

    size = 240
    quiet_zone = 12
    usable_size = size - (quiet_zone * 2)
    qr_widget.x = quiet_zone
    qr_widget.y = quiet_zone
    qr_widget.barWidth = usable_size
    qr_widget.barHeight = usable_size
    drawing = Drawing(size, size)
    drawing.add(qr_widget)

    svg = renderSVG.drawToString(drawing)
    svg_start = svg.find("<svg")
    svg_tag_end = svg.find(">", svg_start) if svg_start != -1 else -1
    if svg_tag_end != -1:
        background = f'<rect x="0" y="0" width="{size}" height="{size}" fill="#050505" />'
        svg = f"{svg[:svg_tag_end + 1]}{background}{svg[svg_tag_end + 1:]}"

    if logo_bytes:
        logo_data = base64.b64encode(logo_bytes).decode("ascii")
        backdrop_size = 38
        logo_size = 28
        backdrop_position = (size - backdrop_size) / 2
        logo_position = (size - logo_size) / 2
        overlay = (
            f'<rect x="{backdrop_position:.1f}" y="{backdrop_position:.1f}" '
            f'width="{backdrop_size}" height="{backdrop_size}" rx="8" ry="8" fill="#050505" />'
            f'<image href="data:image/png;base64,{logo_data}" '
            f'x="{logo_position:.1f}" y="{logo_position:.1f}" '
            f'width="{logo_size}" height="{logo_size}" preserveAspectRatio="xMidYMid meet" />'
        )
        svg = svg.replace("</svg>", f"{overlay}</svg>", 1)
    return svg


def _compact_qr_logo(logo_path: Path) -> bytes | None:
    if not logo_path.is_file():
        return None
    try:
        from PIL import Image

        with Image.open(logo_path) as image:
            image.thumbnail((56, 56), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except (OSError, ValueError):
        return logo_path.read_bytes()


def ensure_team_qr_assets(team: dict[str, Any], team_path: Path, static_dir: Path) -> dict[str, str]:
    """Create static vCard QR assets, regenerating only when team.json changes."""
    output_dir = static_dir / "assets" / "team-qr"
    manifest_path = output_dir / "manifest.json"
    source_bytes = team_path.read_bytes() if team_path.exists() else json.dumps(team, sort_keys=True).encode("utf-8")
    fingerprint = hashlib.sha256(_QR_GENERATOR_VERSION.encode("ascii") + b"\0" + source_bytes).hexdigest()
    members = build_team_members(team)
    asset_paths = {member["slug"]: f"assets/team-qr/{member['slug']}.svg" for member in members}

    with _qr_assets_lock:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            manifest = {}

        assets_exist = all((static_dir / relative_path).is_file() for relative_path in asset_paths.values())
        if manifest.get("team_fingerprint") == fingerprint and assets_exist:
            return asset_paths

        output_dir.mkdir(parents=True, exist_ok=True)
        logo_path = static_dir / "assets" / "ce_logo_shape.png"
        logo_bytes = _compact_qr_logo(logo_path)
        expected_names = {f"{slug}.svg" for slug in asset_paths}
        for member in members:
            # Photos are intentionally omitted: embedding them makes the QR much
            # denser and substantially harder for phone cameras to scan.
            vcard_text = build_member_vcard(member, team)
            target = output_dir / f"{member['slug']}.svg"
            temporary = output_dir / f".{member['slug']}.svg.tmp"
            temporary.write_text(_render_vcard_qr_svg(vcard_text, logo_bytes), encoding="utf-8")
            os.replace(temporary, target)

        for stale_asset in output_dir.glob("*.svg"):
            if stale_asset.name not in expected_names:
                stale_asset.unlink()

        temporary_manifest = output_dir / ".manifest.json.tmp"
        temporary_manifest.write_text(
            json.dumps({"team_fingerprint": fingerprint, "generator_version": _QR_GENERATOR_VERSION}, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_manifest, manifest_path)

    return asset_paths


def slugify(value: str) -> str:
    return _slugify(value)
