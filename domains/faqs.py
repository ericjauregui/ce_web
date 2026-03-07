from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_faqs(faqs_path: Path) -> list[dict[str, Any]]:
    if not faqs_path.exists():
        return []

    with open(faqs_path, "r", encoding="utf-8") as file:
        raw = json.load(file)

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