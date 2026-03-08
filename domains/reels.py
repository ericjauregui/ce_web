from __future__ import annotations

import random
from pathlib import Path


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

        reels.append({"filename": name, "url": f"/static/reels/{name}"})

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
