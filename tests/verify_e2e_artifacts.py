from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tests.run import ROOT, _source_fingerprint


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root: Path, *, check_source: bool = False) -> list[str]:
    problems: list[str] = []
    manifest_path = root / "run-manifest.json"
    if not manifest_path.is_file():
        return [f"Missing {manifest_path}"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evidence = manifest.get("evidence", [])
    if not evidence:
        problems.append("Manifest has no E2E evidence")
    if not manifest.get("successful"):
        problems.append("E2E run did not pass")
    if check_source and manifest.get("source_tree_sha256") != _source_fingerprint():
        problems.append("Source tree changed since this run")
    seen: set[str] = set()
    for record in evidence:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            problems.append(f"Unsafe evidence path: {relative}")
            continue
        path = root / relative
        if not path.is_file():
            problems.append(f"Missing evidence: {relative}")
            continue
        if _sha256(path) != record["sha256"]:
            problems.append(f"Evidence hash mismatch: {relative}")
        item = json.loads(path.read_text(encoding="utf-8"))
        test_id = item.get("test_id", "")
        if test_id in seen:
            problems.append(f"Duplicate test evidence: {test_id}")
        seen.add(test_id)
        if item.get("run_id") != manifest.get("run_id"):
            problems.append(f"Run ID mismatch: {relative}")
        if test_id != record["test_id"] or item.get("status") != record["status"]:
            problems.append(f"Test identity/status mismatch: {relative}")
        if item.get("capture_errors"):
            problems.append(f"Capture errors: {relative}")
        for required in ("page.png", "page.html", "browser-events.txt"):
            if required not in item.get("files_sha256", {}):
                problems.append(f"Missing {required} in {relative}")
        for file_name, expected_hash in item.get("files_sha256", {}).items():
            if Path(file_name).name != file_name:
                problems.append(f"Unsafe artifact file name: {file_name}")
                continue
            file_path = path.parent / file_name
            if not file_path.is_file() or _sha256(file_path) != expected_hash:
                problems.append(f"Artifact hash mismatch: {file_path.relative_to(root)}")
    if manifest.get("successful") and any(record["status"] != "passed" for record in evidence):
        problems.append("Successful manifest includes failed E2E evidence")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify SHA-256 hashes for an E2E run's artifacts.")
    parser.add_argument("--artifacts-dir", type=Path, default=ROOT / ".test-artifacts" / "e2e")
    parser.add_argument("--check-source", action="store_true", help="Also require the current source tree to match the run.")
    args = parser.parse_args()
    problems = verify(args.artifacts_dir, check_source=args.check_source)
    if problems:
        for problem in problems:
            print(problem)
        return 1
    print(f"Verified E2E evidence in {args.artifacts_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
