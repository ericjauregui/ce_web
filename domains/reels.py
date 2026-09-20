from __future__ import annotations

import random
from pathlib import Path

from domains.file_cache import get_path_version


def discover_reels(reels_dir: Path) -> list[dict[str, str]]:
    """Return deterministic reel metadata for non-hidden MP4 files."""
    if not reels_dir.exists() or not reels_dir.is_dir():
        return []

    reels: list[dict[str, str]] = []
    for entry in reels_dir.iterdir():
        name = entry.name
        if name.startswith("."):
            continue
        if not entry.is_file():
            continue
        if entry.suffix.lower() != ".mp4":
            continue

        reel = {"filename": name, "url": f"/static/reels/{name}"}
        poster_name = f"{name}.{get_path_version(entry)}.webp"
        if (reels_dir / "posters" / poster_name).is_file():
            reel["poster"] = f"reels/posters/{poster_name}"
            for width in (160, 320):
                sized = poster_name.removesuffix('.webp') + f'.{width}.webp'
                if (reels_dir / "posters" / sized).is_file():
                    reel[f"poster_{width}"] = f"reels/posters/{sized}"
        reels.append(reel)

    reels.sort(key=lambda reel: reel["filename"].lower())
    return reels


def shuffled_reels(reels: list[dict[str, str]]) -> list[dict[str, str]]:
    randomized = list(reels)
    random.shuffle(randomized)
    return randomized


def load_random_reels(reels_dir: Path, limit: int | None = None) -> list[dict[str, str]]:
    reels = shuffled_reels(discover_reels(reels_dir))
    if limit is None:
        return reels
    return reels[: max(0, limit)]
