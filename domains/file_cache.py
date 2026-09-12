from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Any

# Lightweight in-process cache keyed by absolute file path.
_cache_lock = Lock()
_json_cache: dict[str, tuple[int, int, Any]] = {}
_path_version_cache: dict[str, tuple[int, int, str]] = {}


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


def get_path_version(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None

    resolved = str(path.resolve())
    stat = path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)

    with _cache_lock:
        cached = _path_version_cache.get(resolved)
        if cached and cached[0] == stamp[0] and cached[1] == stamp[1]:
            return cached[2]

        # A content fingerprint stays stable across deploys when the file is
        # unchanged and changes whenever its bytes change. This makes URLs
        # produced by asset_url safe for immutable edge caching.
        version = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        _path_version_cache[resolved] = (stamp[0], stamp[1], version)
        return version
