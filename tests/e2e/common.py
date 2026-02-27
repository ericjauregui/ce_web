from __future__ import annotations

import os
import socket
import threading
import time
import unittest
from contextlib import closing

from werkzeug.serving import make_server

os.environ.setdefault("SECRET_KEY", "test-secret-key")
REQUIRE_E2E = os.environ.get("CE_REQUIRE_E2E") == "1"

import app as webapp


def _find_free_port() -> int:
	with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
		sock.bind(("127.0.0.1", 0))
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		return int(sock.getsockname()[1])


class _LiveServerThread(threading.Thread):
	def __init__(self, flask_app, host: str, port: int) -> None:
		super().__init__(daemon=True)
		self._server = make_server(host, port, flask_app)

	def run(self) -> None:
		self._server.serve_forever()

	def shutdown(self) -> None:
		self._server.shutdown()


class BaseE2ETest(unittest.TestCase):
	browser_name = "chromium"
	viewport = {"width": 1280, "height": 900}

	@classmethod
	def setUpClass(cls) -> None:
		try:
			from playwright.sync_api import sync_playwright
		except Exception as exc:
			message = "Playwright is not installed. Install optional deps and browsers to run E2E tests."
			if REQUIRE_E2E:
				raise RuntimeError(message) from exc
			raise unittest.SkipTest(message) from exc

		webapp.app.config.update(TESTING=True)

		cls._host = "127.0.0.1"
		cls._port = _find_free_port()
		cls.base_url = f"http://{cls._host}:{cls._port}"

		cls._server_thread = _LiveServerThread(webapp.app, cls._host, cls._port)
		cls._server_thread.start()
		time.sleep(0.2)

		cls._playwright_context = sync_playwright().start()
		browser_type = getattr(cls._playwright_context, cls.browser_name)

		try:
			cls._browser = browser_type.launch(headless=True)
		except Exception as exc:
			cls._playwright_context.stop()
			cls._server_thread.shutdown()
			message = (
				f"Playwright browser '{cls.browser_name}' is not available. "
				"Run: python -m playwright install chromium webkit"
			)
			if REQUIRE_E2E:
				raise RuntimeError(message) from exc
			raise unittest.SkipTest(message) from exc

	@classmethod
	def tearDownClass(cls) -> None:
		try:
			cls._browser.close()
		finally:
			cls._playwright_context.stop()
			cls._server_thread.shutdown()

	def setUp(self) -> None:
		self.context = self._browser.new_context(viewport=self.viewport)
		self.page = self.context.new_page()
		self.page.set_default_timeout(60000)
		self.page.set_default_navigation_timeout(60000)

	def tearDown(self) -> None:
		self.context.close()
