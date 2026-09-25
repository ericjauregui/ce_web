from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import unittest
import uuid
from datetime import datetime, timezone
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
        description="Run browser E2E tests and focused isolated checks.",
    )
    parser.add_argument(
        "suite",
        nargs="?",
        default="e2e",
        choices=["standard", "e2e", "all"],
        help="Which suite to run (default: e2e).",
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
        help="Directory where every E2E test writes screenshots, HTML, and browser logs.",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Preserve existing E2E artifacts instead of cleaning them before a new E2E run.",
    )
    return parser.parse_args(argv)


def configure_environment(args: argparse.Namespace) -> None:
    if args.suite in {"e2e", "all"}:
        os.environ["CE_REQUIRE_E2E"] = "1"
        os.environ["CE_E2E_RUN_ID"] = uuid.uuid4().hex
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
    if args.suite in {"e2e", "all"}:
        write_e2e_manifest(args, result)
    return 0 if result.wasSuccessful() else 1


def _source_fingerprint() -> str:
    digest = hashlib.sha256()
    roots = [ROOT / "app.py", ROOT / "domains", ROOT / "templates", ROOT / "catalog", ROOT / "tests", ROOT / "static" / "js", ROOT / "static" / "css"]
    source_paths = []
    for root in roots:
        source_paths.extend([root] if root.is_file() else root.rglob("*"))
    for path in sorted(path for path in source_paths if path.is_file() and path.suffix in {".py", ".html", ".js", ".css", ".json", ".cjs"}):
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def write_e2e_manifest(args: argparse.Namespace, result: unittest.TestResult) -> None:
    artifact_root = Path(os.environ.get("CE_E2E_ARTIFACTS_DIR", str(ROOT / ".test-artifacts" / "e2e")))
    artifact_root.mkdir(parents=True, exist_ok=True)
    run_id = os.environ["CE_E2E_RUN_ID"]
    evidence = []
    for path in sorted(artifact_root.rglob("evidence.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        if item.get("run_id") != run_id:
            continue
        relative = path.relative_to(artifact_root)
        evidence.append({
            "path": str(relative),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "test_id": item["test_id"],
            "status": item["status"],
        })
    git_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "suite": args.suite,
        "browser_override": args.browser,
        "git_commit": git_result.stdout.strip() if git_result.returncode == 0 else None,
        "source_tree_sha256": _source_fingerprint(),
        "tests_run": result.testsRun,
        "failures": [test.id() for test, _ in result.failures],
        "errors": [test.id() for test, _ in result.errors],
        "skipped": [test.id() for test, _ in result.skipped],
        "successful": result.wasSuccessful(),
        "evidence": evidence,
    }
    manifest = artifact_root / "run-manifest.json"
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"E2E evidence: {manifest}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
