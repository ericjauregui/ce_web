from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path


def canonical_base_url(request_url_root: str) -> str:
    configured = (os.getenv("SITE_BASE_URL") or "").strip()
    if configured:
        return configured.rstrip("/")
    return request_url_root.rstrip("/")


def iso_lastmod(*paths: Path) -> str | None:
    valid = [path for path in paths if path.exists()]
    if not valid:
        return None

    latest = max(path.stat().st_mtime for path in valid)
    return datetime.fromtimestamp(latest, tz=UTC).date().isoformat()


def build_sitemap_urls(
    base_url: str,
    *,
    base_dir: Path,
    catalog_path: Path,
    collections_path: Path,
    team_path: Path,
    team_members: list[dict],
) -> list[dict[str, str | float | None]]:
    pages = [
        {
            "path": "/",
            "changefreq": "daily",
            "priority": 1.0,
            "lastmod": iso_lastmod(catalog_path, collections_path, base_dir / "templates" / "index.html"),
        },
        {
            "path": "/about",
            "changefreq": "monthly",
            "priority": 0.7,
            "lastmod": iso_lastmod(base_dir / "templates" / "about.html"),
        },
        {
            "path": "/contact",
            "changefreq": "monthly",
            "priority": 0.7,
            "lastmod": iso_lastmod(base_dir / "templates" / "contact.html"),
        },
        {
            "path": "/team",
            "changefreq": "monthly",
            "priority": 0.8,
            "lastmod": iso_lastmod(team_path, base_dir / "templates" / "team.html"),
        },
    ]

    team_lastmod = iso_lastmod(team_path, base_dir / "templates" / "team_member.html")
    for member in team_members:
        pages.append(
            {
                "path": f"/team/{member.get('slug', '')}",
                "changefreq": "monthly",
                "priority": 0.6,
                "lastmod": team_lastmod,
            }
        )

    return [
        {
            "loc": f"{base_url}{page['path']}",
            "lastmod": page["lastmod"],
            "changefreq": page["changefreq"],
            "priority": page["priority"],
        }
        for page in pages
    ]
