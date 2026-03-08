from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

# Lightweight in-process cache keyed by absolute file path.
_cache_lock = Lock()
_json_cache: dict[str, tuple[int, int, Any]] = {}


def load_json_cached(path: Path, default: Any) -> Any:
    resolved = str(path.resolve())

    if not path.exists():
        return default

    stat = path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)

    with _cache_lock:
        cached = _json_cache.get(resolved)
        if cached and cached[0] == stamp[0] and cached[1] == stamp[1]:
            return cached[2]

    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    with _cache_lock:
        _json_cache[resolved] = (stamp[0], stamp[1], data)

    return data
