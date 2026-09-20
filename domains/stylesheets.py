"""Serve the optimized stylesheet only while its source inventory is current."""
import json
from pathlib import Path
from functools import lru_cache
from domains.file_cache import get_path_version


def css_inputs(root: Path) -> list[Path]:
    return sorted([*root.glob('templates/**/*.html'), *root.glob('static/js/**/*.js'),
                   *root.glob('static/css/styles/**/*.css'), *root.glob('domains/*.py'), root / 'app.py'])


@lru_cache(maxsize=8)
def _manifest(path: Path, version: str):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def bootstrap_stylesheet(root: Path) -> str:
    fallback = 'vendor/bootstrap/bootstrap.min.css'
    path = root / 'static/css/bootstrap.site.manifest.json'
    version = get_path_version(path)
    if not version:
        return fallback
    manifest = _manifest(path, version)
    expected = {str(p.relative_to(root)) for p in css_inputs(root)}
    if not expected.issubset(manifest):
        return fallback
    if not manifest or any(get_path_version(root / name) != value for name, value in manifest.items()):
        return fallback
    return 'css/bootstrap.site.min.css'
