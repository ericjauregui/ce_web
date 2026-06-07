from __future__ import annotations

import os
import shutil
import socket
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from werkzeug.serving import make_server

os.environ.setdefault("SECRET_KEY", "test-secret-key")
REQUIRE_E2E = os.environ.get("CE_REQUIRE_E2E") == "1"
_ARTIFACT_ROOT_PREPARED = False

import app as webapp
from domains.location_options import (
	CHECKOUT_COUNTRY_LABELS_BY_KEY,
	CHECKOUT_COUNTRY_OPTIONS,
	CHECKOUT_SUBDIVISION_OPTIONS_BY_COUNTRY_KEY,
)


def _find_free_port() -> int:
	with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
		sock.bind(("127.0.0.1", 0))
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		return int(sock.getsockname()[1])


def _wait_for_server_ready(url: str, timeout_seconds: float = 10.0) -> None:
	deadline = time.time() + timeout_seconds
	last_error: Exception | None = None
	while time.time() < deadline:
		try:
			with urlopen(url, timeout=1.0) as response:
				if response.status < 500:
					return
		except URLError as exc:
			last_error = exc
		time.sleep(0.1)
	message = f"Timed out waiting for live test server at {url}"
	if last_error is not None:
		raise RuntimeError(message) from last_error
	raise RuntimeError(message)


def _artifact_root() -> Path:
	default_root = Path(webapp.BASE_DIR) / ".test-artifacts" / "e2e"
	return Path(os.environ.get("CE_E2E_ARTIFACTS_DIR", str(default_root)))


def _prepare_artifact_root() -> None:
	global _ARTIFACT_ROOT_PREPARED
	if _ARTIFACT_ROOT_PREPARED:
		return

	artifact_root = _artifact_root()
	should_clean = os.environ.get("CE_E2E_CLEAN_ARTIFACTS", "1") != "0"
	if should_clean and artifact_root.exists():
		shutil.rmtree(artifact_root)

	_ARTIFACT_ROOT_PREPARED = True


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
	enforce_clean_browser = False

	@staticmethod
	def is_ignored_page_error(error_message: str) -> bool:
		return False

	@staticmethod
	def is_ignored_console_message(message: str) -> bool:
		return False

	@staticmethod
	def is_ignored_request_failure(message: str) -> bool:
		return False

	@classmethod
	def setUpClass(cls) -> None:
		try:
			from playwright.sync_api import sync_playwright
		except Exception as exc:
			message = "Playwright is not installed. Install optional deps and browsers to run E2E tests."
			if REQUIRE_E2E:
				raise RuntimeError(message) from exc
			raise unittest.SkipTest(message) from exc

		_prepare_artifact_root()
		webapp.app.config.update(TESTING=True)
		cls.valid_code = webapp.load_products()[0]["code"]
		cls.us_country_label = CHECKOUT_COUNTRY_LABELS_BY_KEY["us"]
		cls.country_without_subdivisions_key, cls.country_without_subdivisions_label = next(
			(
				(key, label)
				for key, label in CHECKOUT_COUNTRY_OPTIONS
				if not CHECKOUT_SUBDIVISION_OPTIONS_BY_COUNTRY_KEY.get(key)
			),
			("", ""),
		)

		cls._host = "127.0.0.1"
		cls._port = _find_free_port()
		cls.base_url = f"http://{cls._host}:{cls._port}"

		cls._server_thread = _LiveServerThread(webapp.app, cls._host, cls._port)
		cls._server_thread.start()
		try:
			_wait_for_server_ready(cls.base_url)
		except Exception:
			cls._server_thread.shutdown()
			cls._server_thread.join(timeout=2)
			raise

		cls._playwright_context = sync_playwright().start()
		browser_name = os.environ.get("CE_E2E_BROWSER") or cls.browser_name
		browser_type = getattr(cls._playwright_context, browser_name, None)
		if browser_type is None:
			cls._playwright_context.stop()
			cls._server_thread.shutdown()
			cls._server_thread.join(timeout=2)
			message = f"Unknown Playwright browser '{browser_name}'. Use chromium, webkit, or firefox."
			raise RuntimeError(message)

		try:
			headless = os.environ.get("CE_E2E_HEADLESS", "1") != "0"
			launch_options = {"headless": headless}
			if browser_name == "chromium":
				launch_options["channel"] = "chromium"
			cls._browser = browser_type.launch(**launch_options)
		except Exception as exc:
			cls._playwright_context.stop()
			cls._server_thread.shutdown()
			cls._server_thread.join(timeout=2)
			message = (
				f"Playwright browser '{browser_name}' is not available. "
				"Run: python -m playwright install chromium webkit"
			)
			if REQUIRE_E2E:
				raise RuntimeError(message) from exc
			raise unittest.SkipTest(message) from exc

		cls.browser_name = browser_name

	@classmethod
	def tearDownClass(cls) -> None:
		browser = getattr(cls, "_browser", None)
		playwright_context = getattr(cls, "_playwright_context", None)
		server_thread = getattr(cls, "_server_thread", None)
		try:
			if browser is not None:
				browser.close()
		finally:
			try:
				if playwright_context is not None:
					playwright_context.stop()
			finally:
				if server_thread is not None:
					server_thread.shutdown()
					server_thread.join(timeout=2)

	def setUp(self) -> None:
		self.context = self._browser.new_context(viewport=self.viewport)
		self.page = self.context.new_page()
		self.page.set_default_timeout(60000)
		self.page.set_default_navigation_timeout(60000)
		self.console_errors: list[str] = []
		self.page_errors: list[str] = []
		self.request_failures: list[str] = []
		self.page.on("console", self._record_console_message)
		self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
		self.page.on("requestfailed", self._record_request_failure)

	def tearDown(self) -> None:
		try:
			if self.enforce_clean_browser:
				self.assert_browser_clean()
		except Exception:
			self._write_failure_artifacts()
			raise
		finally:
			if self._current_test_failed():
				self._write_failure_artifacts()
			self.context.close()

	def goto(self, path: str, *, wait_until: str = "domcontentloaded"):
		target = path if path.startswith("http") else f"{self.base_url}{path}"
		response = self.page.goto(target, wait_until=wait_until)
		self.assertIsNotNone(response, f"Navigation to {target} did not produce a response")
		if response is not None:
			self.assertLess(response.status, 400, f"Navigation to {target} returned {response.status}")
		return response

	def add_first_catalog_item_to_cart(self) -> None:
		self.goto("/")
		button = self.page.locator(".add-to-cart-btn").first
		button.scroll_into_view_if_needed()
		button.click()
		self.page.wait_for_function(
			"""
			() => {
			  const badge = document.getElementById('cartCountBadge');
			  return badge && Number(badge.textContent || '0') > 0;
			}
			"""
		)

	def open_checkout_with_item(self) -> None:
		self.add_first_catalog_item_to_cart()
		self.goto("/checkout")

	def assert_browser_clean(self) -> None:
		unexpected_page_errors = [
			message for message in self.page_errors
			if not self.is_ignored_page_error(message)
		]
		unexpected_console_errors = [
			message for message in self.console_errors
			if not self.is_ignored_console_message(message)
		]
		unexpected_request_failures = [
			message for message in self.request_failures
			if not self.is_ignored_request_failure(message)
		]

		if not unexpected_page_errors and not unexpected_console_errors and not unexpected_request_failures:
			return

		self._write_failure_artifacts()
		sections: list[str] = []
		if unexpected_page_errors:
			sections.append("Page errors:\n" + "\n".join(unexpected_page_errors))
		if unexpected_console_errors:
			sections.append("Console errors:\n" + "\n".join(unexpected_console_errors))
		if unexpected_request_failures:
			sections.append("Request failures:\n" + "\n".join(unexpected_request_failures))
		self.fail("Unexpected browser issues detected:\n\n" + "\n\n".join(sections))

	def _record_console_message(self, message) -> None:
		if getattr(message, "type", "") != "error":
			return
		self.console_errors.append(str(getattr(message, "text", "") or message))

	def _record_request_failure(self, request) -> None:
		failure = getattr(request, "failure", None)
		failure_text = str(failure or "request failed")
		self.request_failures.append(f"{failure_text} :: {request.method} {request.url}")

	def _current_test_failed(self) -> bool:
		outcome = getattr(self, "_outcome", None)
		if outcome is None:
			return False
		result = getattr(outcome, "result", None)
		if result is None:
			return False
		failures = list(getattr(result, "failures", []))
		errors = list(getattr(result, "errors", []))
		return any(test_case is self for test_case, _ in [*failures, *errors])

	def _artifact_dir(self) -> Path:
		safe_test_id = self.id().replace(os.sep, "_").replace(":", "_")
		return _artifact_root() / self.browser_name / safe_test_id

	def _write_failure_artifacts(self) -> None:
		artifact_dir = self._artifact_dir()
		artifact_dir.mkdir(parents=True, exist_ok=True)

		page = getattr(self, "page", None)
		if page is not None:
			try:
				page.screenshot(path=str(artifact_dir / "page.png"), full_page=True)
			except Exception:
				pass
			try:
				(artifact_dir / "page.html").write_text(page.content(), encoding="utf-8")
			except Exception:
				pass

		log_lines = [f"URL: {getattr(page, 'url', '')}"]
		if self.page_errors:
			log_lines.extend(["", "[page errors]", *self.page_errors])
		if self.console_errors:
			log_lines.extend(["", "[console errors]", *self.console_errors])
		if self.request_failures:
			log_lines.extend(["", "[request failures]", *self.request_failures])
		(artifact_dir / "browser-events.txt").write_text("\n".join(log_lines), encoding="utf-8")
