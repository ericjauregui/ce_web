from __future__ import annotations

from pathlib import Path
from typing import Any

from domains.file_cache import load_json_cached


def load_faqs(faqs_path: Path) -> list[dict[str, Any]]:
    if not faqs_path.exists():
        return []

    raw = load_json_cached(faqs_path, [])

    if not isinstance(raw, list):
        return []

    items: list[dict[str, Any]] = []
    for entry in raw:
        item = entry if isinstance(entry, dict) else {}
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not question or not answer:
            continue
        items.append({"question": question, "answer": answer})

    return items