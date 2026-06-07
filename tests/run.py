from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"
E2E_DIR = TESTS_DIR / "e2e"


def build_suite(name: str) -> unittest.TestSuite:
    loader = unittest.defaultTestLoader

    if name == "standard":
        return loader.discover(
            start_dir=str(TESTS_DIR),
            pattern="test*.py",
            top_level_dir=str(ROOT),
        )

    if name == "e2e":
        return loader.discover(
            start_dir=str(E2E_DIR),
            pattern="e2e_*.py",
            top_level_dir=str(ROOT),
        )

    suite = unittest.TestSuite()
    suite.addTests(build_suite("standard"))
    suite.addTests(build_suite("e2e"))
    return suite


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the CE web test suite with consistent unit/contract/e2e entry points.",
    )
    parser.add_argument(
        "suite",
        nargs="?",
        default="standard",
        choices=["standard", "e2e", "all"],
        help="Which suite to run.",
    )
    parser.add_argument("-v", "--verbosity", type=int, default=2)
    parser.add_argument("-f", "--failfast", action="store_true")
    parser.add_argument(
        "--browser",
        choices=["chromium", "webkit", "firefox"],
        help="Override the default Playwright browser for E2E suites.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run Playwright browsers headed instead of headless.",
    )
    parser.add_argument(
        "--require-e2e",
        action="store_true",
        help="Treat missing Playwright dependencies/browsers as hard failures instead of skips.",
    )
    parser.add_argument(
        "--artifacts-dir",
        help="Directory where failing E2E tests should write screenshots and browser logs.",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Preserve existing E2E artifacts instead of cleaning them before a new E2E run.",
    )
    return parser.parse_args(argv)


def configure_environment(args: argparse.Namespace) -> None:
    if args.browser:
        os.environ["CE_E2E_BROWSER"] = args.browser
    if args.headed:
        os.environ["CE_E2E_HEADLESS"] = "0"
    if args.require_e2e:
        os.environ["CE_REQUIRE_E2E"] = "1"
    if args.artifacts_dir:
        os.environ["CE_E2E_ARTIFACTS_DIR"] = args.artifacts_dir
    if args.keep_artifacts:
        os.environ["CE_E2E_CLEAN_ARTIFACTS"] = "0"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_environment(args)

    runner = unittest.TextTestRunner(
        verbosity=args.verbosity,
        failfast=args.failfast,
    )
    result = runner.run(build_suite(args.suite))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())