from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import app as webapp


class BaseWebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        webapp.app.config.update(TESTING=True)
        cls.client = webapp.app.test_client()
        cls.valid_code = webapp.load_products()[0]["code"]
        cls.team_members = webapp.build_team_members(webapp.load_team())
        cls.first_member = cls.team_members[0] if cls.team_members else {"slug": "", "name": ""}

    def setUp(self) -> None:
        with self.client.session_transaction() as sess:
            sess["cart"] = {}

    @staticmethod
    def load_site_css() -> str:
        root_css = Path(webapp.BASE_DIR) / "static" / "css" / "style.css"
        import_pattern = re.compile(r"@import\s+url\(\s*[\"'](?P<path>[^\"']+)[\"']\s*\)\s*;")

        def read_with_imports(path: Path, seen: set[Path]) -> str:
            resolved = path.resolve()
            if resolved in seen:
                return ""
            seen.add(resolved)

            content = path.read_text(encoding="utf-8")

            def repl(match: re.Match[str]) -> str:
                rel = match.group("path")
                imported = (path.parent / rel).resolve()
                return read_with_imports(imported, seen)

            return import_pattern.sub(repl, content)

        return read_with_imports(root_css, set())
