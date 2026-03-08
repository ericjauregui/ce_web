from __future__ import annotations

import tempfile
from pathlib import Path

import app as webapp
from tests.common import BaseWebTest


class ReelsRouteTests(BaseWebTest):
    def test_reels_route_lists_only_visible_mp4_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reels_dir = Path(temp_dir)
            (reels_dir / "b_clip.MP4").write_bytes(b"")
            (reels_dir / "a_clip.mp4").write_bytes(b"")
            (reels_dir / ".hidden.mp4").write_bytes(b"")
            (reels_dir / "ignore.mov").write_bytes(b"")
            (reels_dir / "nested").mkdir()
            (reels_dir / "nested" / "nested.mp4").write_bytes(b"")

            original_path = webapp.REELS_PATH
            webapp.REELS_PATH = reels_dir
            try:
                response = self.client.get("/reels")
            finally:
                webapp.REELS_PATH = original_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)

        self.assertIn("/static/reels/a_clip.mp4", body)
        self.assertIn("/static/reels/b_clip.MP4", body)
        self.assertNotIn("/static/reels/.hidden.mp4", body)
        self.assertNotIn("/static/reels/ignore.mov", body)
        self.assertIn("reels-track-shell scroll-cue-shell scroll-cue-shell--reels", body)
        self.assertIn("class=\"reel-row inline-reel-track scroll-cue-track\"", body)
        self.assertIn("id=\"reelRow\"", body)
        self.assertEqual(body.count('class="reel-card inline-reel-card"'), 2)
        self.assertIn("class=\"reel-card inline-reel-card\"", body)
        self.assertIn("class=\"reel-placeholder inline-reel-placeholder\"", body)
        self.assertIn("class=\"inline-reel-hitbox\"", body)
        self.assertIn("src=\"/static/reels/", body)
        self.assertIn("data-src=\"/static/reels/a_clip.mp4\"", body)
        self.assertIn("preload=\"none\"", body)
        self.assertIn("/static/js/scroll_cue.js", body)
        self.assertIn("/static/js/inline_reels.js", body)
        self.assertIn("/static/js/reels.js", body)
        self.assertNotIn("id=\"reelsAudioGate\"", body)
        self.assertNotIn("id=\"reelsData\"", body)
        self.assertNotIn("data-reel-name=", body)
        self.assertNotIn(">a_clip.mp4<", body)
        self.assertNotIn("reels-status-row", body)
        self.assertNotIn("data-action=\"toggle-audio\"", body)
        self.assertNotIn("data-action=\"collapse\"", body)
        self.assertNotIn("Reels pages", body)
        self.assertNotIn("Page 1 of", body)

    def test_reels_route_shows_empty_state_when_no_mp4_files_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reels_dir = Path(temp_dir)
            (reels_dir / "notes.txt").write_text("hello", encoding="utf-8")

            original_path = webapp.REELS_PATH
            webapp.REELS_PATH = reels_dir
            try:
                response = self.client.get("/reels")
            finally:
                webapp.REELS_PATH = original_path

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("No reels available yet.", body)
        self.assertNotIn("/static/js/scroll_cue.js", body)
        self.assertNotIn("/static/js/reels.js", body)
        self.assertNotIn("/static/js/inline_reels.js", body)

    def test_reels_route_shows_all_reels_on_single_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reels_dir = Path(temp_dir)
            for idx in range(60):
                (reels_dir / f"clip_{idx:02d}.mp4").write_bytes(b"")

            original_path = webapp.REELS_PATH
            webapp.REELS_PATH = reels_dir
            try:
                response = self.client.get("/reels")
            finally:
                webapp.REELS_PATH = original_path

        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body.count('class="reel-card inline-reel-card"'), 60)
        self.assertIn("clip_00.mp4", body)
        self.assertIn("clip_59.mp4", body)
        self.assertNotIn("Reels pages", body)
        self.assertNotIn("Page 1 of", body)
