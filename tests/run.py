from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import multiprocessing
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"
E2E_DIR = TESTS_DIR / "e2e"
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def clean_project_caches() -> None:
    """Remove disposable Python/test caches, without traversing user data."""
    for root in (ROOT, ROOT / "domains", ROOT / "migrations", ROOT / "scripts", TESTS_DIR):
        if not root.is_dir():
            continue
        for current, dirs, _ in os.walk(root, followlinks=False):
            base = Path(current)
            for name in list(dirs):
                path = base / name
                if name == "__pycache__" and not path.is_symlink():
                    shutil.rmtree(path)
                    dirs.remove(name)
                elif path.is_symlink() or (root == ROOT and base == ROOT):
                    dirs.remove(name)
    for name in (".pytest_cache", ".ruff_cache"):
        path = ROOT / name
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)


def prune_old_test_runs(root: Path) -> int:
    """Remove recognized old E2E runs, preserving explicitly named live evidence."""
    base = ROOT / ".test-artifacts"
    if root.resolve() != (base / "e2e").resolve() or not base.is_dir():
        return 0
    removed = 0
    for candidate in base.iterdir():
        if candidate == root or candidate.is_symlink() or not candidate.is_dir():
            continue
        if any(word in candidate.name.lower() for word in ("production", "live")) or (candidate / ".ce-e2e-preserve").exists():
            continue
        manifest = candidate / "run-manifest.json"
        if manifest.is_file() and not manifest.is_symlink():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data.get("evidence"), list) or not isinstance(data.get("tests_run"), int):
                continue
            last_write = manifest.stat().st_mtime
        else:
            # Direct unittest E2E runs have browser directories and individual
            # evidence records but no run manifest. Do not remove mixed folders.
            children = list(candidate.iterdir())
            if not children or any(child.is_symlink() or not child.is_dir() or child.name not in {"chromium", "webkit", "firefox"} for child in children):
                continue
            records = list(candidate.rglob("evidence.json"))
            if not records:
                continue
            try:
                if any(not isinstance((data := json.loads(record.read_text(encoding="utf-8"))).get("files_sha256"), dict)
                       or not isinstance(data.get("test_id"), str) for record in records):
                    continue
                last_write = max(record.stat().st_mtime for record in records)
            except (OSError, ValueError, AttributeError):
                continue
        if time.time() - last_write < 7 * 24 * 3600:
            continue
        shutil.rmtree(candidate)
        removed += 1
    return removed


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
    parser.add_argument("--workers", type=int, default=4, help="Isolated E2E worker processes (default: 4; use 1 for serial).")
    parser.add_argument("--test", action="append", help="Run an exact E2E test ID; repeat to select several.")
    parser.add_argument("--_worker", help=argparse.SUPPRESS)
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
    if args._worker:
        return run_worker(Path(args._worker), args)
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    if args.test and args.suite != "e2e":
        raise SystemExit("--test requires the e2e suite")
    if args.test and not args.artifacts_dir:
        raise SystemExit("--test requires a separate --artifacts-dir")
    configure_environment(args)
    lock_handle = None
    try:
        if args.suite in {"e2e", "all"}:
            root = Path(os.environ.get("CE_E2E_ARTIFACTS_DIR", str(ROOT / ".test-artifacts" / "e2e"))).resolve()
            # One suite per checkout: prevents cleanup of another active run,
            # even when that run selected a different artifact directory.
            lock_name = hashlib.sha256(str(ROOT).encode("utf-8")).hexdigest()[:20]
            lock_handle = (Path(tempfile.gettempdir()) / f"ce-e2e-{lock_name}.lock").open("w")
            try:
                fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit("An E2E run is already using this checkout")
            default_root = (ROOT / ".test-artifacts" / "e2e").resolve()
            if root != default_root and root.exists() and any(root.iterdir()) and not (root / ".ce-e2e-owned").is_file():
                raise SystemExit(f"Refusing to clean unowned artifact directory: {root}")
            if args.workers > 1 and not args.failfast:
                status = run_parallel(args)
            else:
                runner = unittest.TextTestRunner(verbosity=args.verbosity, failfast=args.failfast)
                suite = build_suite(args.suite)
                if args.test:
                    selected = set(args.test)
                    available = {test.id(): test for test in _flatten(suite)}
                    if selected - available.keys():
                        raise SystemExit(f"Unknown E2E test IDs: {sorted(selected - available.keys())}")
                    suite = unittest.TestSuite(available[name] for name in sorted(selected))
                result = runner.run(suite)
                write_e2e_manifest(args, result)
                status = 0 if result.wasSuccessful() else 1
            root.mkdir(parents=True, exist_ok=True)
            (root / ".ce-e2e-owned").write_text("Managed by tests.run\n", encoding="utf-8")
            if status == 0:
                from tests.verify_e2e_artifacts import verify
                problems = verify(root, check_source=True)
                if problems:
                    for problem in problems:
                        print(problem, file=sys.stderr)
                    return 1
                if not args.keep_artifacts:
                    for log in root.glob("worker-*.log"):
                        if log.is_file() and not log.is_symlink():
                            log.unlink()
                    removed = 0 if args.test else prune_old_test_runs(root)
                    if removed:
                        print(f"Removed {removed} older E2E run directories.", file=sys.stderr)
            return status
        runner = unittest.TextTestRunner(verbosity=args.verbosity, failfast=args.failfast)
        return 0 if runner.run(build_suite(args.suite)).wasSuccessful() else 1
    finally:
        if lock_handle is not None:
            lock_handle.close()
        clean_project_caches()


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


def _weight(test_id: str) -> int:
    # Larger journeys visit many pages/widths or intentionally wait on faults.
    if "test_page_titles_leave_room" in test_id or "test_catalog_buttons_use_one_line" in test_id:
        return 20
    if "test_page_titles_team_and_faq" in test_id or "test_page_titles_about_and_contact" in test_id:
        return 10
    if "test_page_titles_reels" in test_id:
        return 5
    if "test_all_page_titles" in test_id:
        return 12
    if "test_compact_navbar_" in test_id:
        return 6
    if "test_other_pages_have_compact" in test_id or "test_catalog_and_browse_pages" in test_id:
        return 8
    if "test_last_removed_item_expires" in test_id or "test_full_resolution_hero" in test_id:
        return 5
    return 1


class TimedResult(unittest.TextTestResult):
    def startTest(self, test):
        super().startTest(test)
        self._started = time.monotonic()

    def stopTest(self, test):
        if not hasattr(self, "ce_durations"):
            self.ce_durations = {}
        self.ce_durations[test.id()] = round(time.monotonic() - self._started, 3)
        super().stopTest(test)


def run_worker(config_path: Path, args: argparse.Namespace) -> int:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    os.environ.update(config["environment"])
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in config["tests"])
    start = time.monotonic()
    result = unittest.TextTestRunner(verbosity=args.verbosity, failfast=False, resultclass=TimedResult).run(suite)
    summary = {
        "tests_run": result.testsRun,
        "failures": [test.id() for test, _ in result.failures],
        "errors": [test.id() for test, _ in result.errors],
        "skipped": [test.id() for test, _ in result.skipped],
        "successful": result.wasSuccessful(),
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "test_durations": getattr(result, "ce_durations", {}),
    }
    Path(config["summary"]).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


def pool_worker(index, tasks, outputs, environment, log_path, verbosity):
    os.environ.update(environment)
    with open(log_path, "w", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            while True:
                task = tasks.get()
                if task is None:
                    break
                batch_id, names = task
                start = time.monotonic()
                try:
                    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in names)
                    result = unittest.TextTestRunner(stream=log, verbosity=verbosity, resultclass=TimedResult).run(suite)
                    summary = {
                        "tests_run": result.testsRun,
                        "failures": [test.id() for test, _ in result.failures],
                        "errors": [test.id() for test, _ in result.errors],
                        "skipped": [test.id() for test, _ in result.skipped],
                        "successful": result.wasSuccessful(),
                        "test_durations": getattr(result, "ce_durations", {}),
                    }
                except Exception as exc:
                    summary = {"tests_run": 0, "failures": [], "errors": [f"batch {batch_id}: {type(exc).__name__}: {exc}"],
                               "skipped": [], "successful": False, "test_durations": {}}
                summary.update({"batch": batch_id, "worker": index, "elapsed_seconds": round(time.monotonic() - start, 3)})
                log.flush()
                outputs.put(summary)
        finally:
            from tests.e2e.common import close_shared_runtime
            close_shared_runtime()


def run_parallel(args: argparse.Namespace) -> int:
    start = time.monotonic()
    result_standard = None
    if args.suite == "all":
        result_standard = unittest.TextTestRunner(verbosity=args.verbosity).run(build_suite("standard"))
    tests = list(_flatten(build_suite("e2e")))
    test_ids = [test.id() for test in tests]
    if args.test:
        selected = set(args.test)
        if selected - set(test_ids):
            raise SystemExit(f"Unknown E2E test IDs: {sorted(selected - set(test_ids))}")
        test_ids = [name for name in test_ids if name in selected]
    if len(test_ids) != len(set(test_ids)):
        raise RuntimeError("Duplicate E2E test IDs")
    root = Path(os.environ.get("CE_E2E_ARTIFACTS_DIR", str(ROOT / ".test-artifacts" / "e2e"))).resolve()
    previous_durations = {}
    previous_manifest = root / "run-manifest.json"
    if previous_manifest.is_file():
        try:
            previous = json.loads(previous_manifest.read_text(encoding="utf-8"))
            for worker in previous.get("workers") or []:
                for name, seconds in worker.get("test_durations", {}).items():
                    if isinstance(seconds, (int, float)) and 0 < seconds < 3600:
                        previous_durations[name] = seconds
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    if not args.keep_artifacts and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    # Keep most class fixtures together; split long UI classes into smaller
    # groups so free workers can pull the next group dynamically.
    count = min(args.workers, len(test_ids))
    if count == 0:
        raise RuntimeError("No E2E tests discovered")

    def estimated_cost(name):
        return previous_durations.get(name, _weight(name) * 8)

    classes = {}
    for name in test_ids:
        classes.setdefault(name.rsplit(".", 1)[0], []).append(name)
    batches = []
    for class_name, names in classes.items():
        if class_name.endswith(".UXE2ETests"):
            groups = min(len(names), count * 2)
        elif class_name.endswith((".NavLayoutE2ETests", ".PageTitleE2ETests")):
            groups = min(len(names), count)
        else:
            groups = 1
        shards = [[] for _ in range(groups)]
        costs = [0.0] * groups
        for name in sorted(names, key=lambda item: (-estimated_cost(item), item)):
            index = min(range(groups), key=lambda i: (costs[i], i))
            shards[index].append(name)
            costs[index] += estimated_cost(name)
        batches.extend((cost, sorted(shard)) for cost, shard in zip(costs, shards) if shard)
    batches.sort(key=lambda batch: -batch[0])
    batch_count = len(batches)
    source_before = _source_fingerprint()
    context = multiprocessing.get_context("spawn")
    tasks = context.Queue()
    outputs = context.Queue()
    for batch_id, (_, names) in enumerate(batches):
        tasks.put((batch_id, names))
    for _ in range(count):
        tasks.put(None)
    processes = []
    for index in range(count):
        env = {key: os.environ[key] for key in ("CE_E2E_RUN_ID", "CE_REQUIRE_E2E", "CE_E2E_BROWSER", "CE_E2E_HEADLESS") if key in os.environ}
        env.update({"CE_E2E_ARTIFACTS_DIR": str(root / f"worker-{index}"), "CE_E2E_CLEAN_ARTIFACTS": "0", "CE_E2E_SHARED_RUNTIME": "1"})
        process = context.Process(target=pool_worker, args=(index, tasks, outputs, env, root / f"worker-{index}.log", args.verbosity))
        process.start()
        processes.append(process)
    results = []
    # Drain results while children run so a full IPC pipe cannot deadlock join.
    while len(results) < batch_count:
        try:
            results.append(outputs.get(timeout=1))
        except queue.Empty:
            if not any(process.is_alive() for process in processes):
                break
    for process in processes:
        process.join()
    missing = batch_count - len(results)
    if missing:
        results.append({"tests_run": 0, "failures": [], "errors": [f"{missing} E2E batches did not report results"],
                        "skipped": [], "successful": False, "test_durations": {}, "elapsed_seconds": None})
    for index, process in enumerate(processes):
        if process.exitcode:
            results.append({"tests_run": 0, "failures": [], "errors": [f"worker {index} exited with code {process.exitcode}"],
                            "skipped": [], "successful": False, "test_durations": {}, "elapsed_seconds": None})
    tasks.close()
    outputs.close()
    failures = [(SimpleNamespace(id=lambda name=name: name), "") for data in results for name in data["failures"]]
    errors = [(SimpleNamespace(id=lambda name=name: name), "") for data in results for name in data["errors"]]
    skipped = [(SimpleNamespace(id=lambda name=name: name), "") for data in results for name in data["skipped"]]
    if result_standard is not None:
        failures.extend(result_standard.failures)
        errors.extend(result_standard.errors)
        skipped.extend(result_standard.skipped)
    if sum(data["tests_run"] for data in results) != len(test_ids):
        errors.append((SimpleNamespace(id=lambda: "E2E discovery/execution count mismatch"), ""))
    if _source_fingerprint() != source_before:
        errors.append((SimpleNamespace(id=lambda: "Source tree changed during E2E run"), ""))
    actual_ids = []
    for path in root.rglob("evidence.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        if item.get("run_id") == os.environ["CE_E2E_RUN_ID"]:
            actual_ids.append(item.get("test_id"))
    skipped_ids = {test.id() for test, _ in skipped}
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(test_ids) - skipped_ids:
        errors.append((SimpleNamespace(id=lambda: "E2E evidence missing, duplicated, or unexpected"), ""))
    result = SimpleNamespace(testsRun=sum(data["tests_run"] for data in results) + (result_standard.testsRun if result_standard else 0), failures=failures, errors=errors, skipped=skipped)
    result.wasSuccessful = lambda: not result.failures and not result.errors
    write_e2e_manifest(args, result, expected_e2e=test_ids, workers=results, elapsed=time.monotonic() - start)
    print(f"Ran {result.testsRun} tests with {count} E2E workers ({batch_count} batches) in {time.monotonic() - start:.1f}s; failures={len(failures)}, errors={len(errors)}, skipped={len(skipped)}", file=sys.stderr)
    for test, _ in failures + errors:
        print(f"FAILED: {test.id()}", file=sys.stderr)
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


def write_e2e_manifest(args: argparse.Namespace, result: unittest.TestResult, *, expected_e2e=None, workers=None, elapsed=None) -> None:
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
        "expected_e2e": expected_e2e,
        "workers": workers,
        "elapsed_seconds": round(elapsed, 3) if elapsed is not None else None,
    }
    manifest = artifact_root / "run-manifest.json"
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"E2E evidence: {manifest}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
