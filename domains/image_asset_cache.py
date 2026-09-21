"""Bounded cache of validated static image metadata; never stores page/cart data."""
from collections import OrderedDict
from dataclasses import dataclass
import os
from pathlib import Path
from threading import RLock

from domains.file_cache import get_path_version, load_json_cached


@dataclass(frozen=True)
class ImageSelection:
    path: str
    version: str | None
    # Immutable (path, width, version) records; no caller can mutate cached data.
    candidates: tuple[tuple[str, int, str | None], ...] = ()


@dataclass(frozen=True)
class ManifestSnapshot:
    generation: tuple
    lossless: dict
    responsive: dict
    heroes: dict


def _stamp(filename: str):
    try:
        stat = os.stat(filename)
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


class ImageAssetCache:
    def __init__(self, static_root: Path, max_entries: int = 1024):
        self.root = static_root
        self.max_entries = max_entries
        self._lock = RLock()
        self._snapshot = None
        self._entries = OrderedDict()
        self._manifests = tuple(static_root / 'optimized' / name for name in (
            'manifest.json', 'responsive-manifest.json', 'hero-manifest.json'))

    def snapshot(self) -> ManifestSnapshot:
        """Check three manifest stamps once per request, parse only on change."""
        generation = tuple(_stamp(str(path)) for path in self._manifests)
        with self._lock:
            if self._snapshot is None or self._snapshot.generation != generation:
                manifests = [load_json_cached(path, {}) for path in self._manifests]
                self._snapshot = ManifestSnapshot(generation, *manifests)
                self._entries.clear()
            return self._snapshot

    def get(self, filename: str, snapshot: ManifestSnapshot, *, hero: bool = False) -> ImageSelection:
        key = filename, hero
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                generation, dependencies, stamps, result = cached
                if generation == snapshot.generation and stamps == tuple(_stamp(path) for path in dependencies):
                    self._entries.move_to_end(key)
                    return result

            dependencies = {filename}
            lossless = snapshot.lossless.get(filename)
            responsive = snapshot.responsive.get(filename)
            hero_entry = snapshot.heroes.get(filename) if hero else None
            for entry in (lossless, hero_entry):
                if entry:
                    dependencies.add(entry['path'])
            if responsive:
                dependencies.update(item['path'] for item in responsive['candidates'])
            paths = tuple(str(self.root / name) for name in sorted(dependencies))
            stamps = tuple(_stamp(path) for path in paths)

            source_version = get_path_version(self.root / filename)
            selected, version = filename, source_version
            for entry in (lossless, hero_entry):
                if (entry and entry['source_version'] == source_version
                        and get_path_version(self.root / entry['path']) == entry['version']):
                    selected, version = entry['path'], entry['version']
            candidates = []
            if responsive and responsive['source_version'] == source_version:
                candidates = [(item['path'], item['width'], item['version'])
                              for item in responsive['candidates']
                              if get_path_version(self.root / item['path']) == item['version']]
                if candidates:
                    candidates.append((selected, responsive['width'], version))
            result = ImageSelection(selected, version, tuple(candidates))
            # A file changed while validating: return the result, but do not cache it.
            if stamps == tuple(_stamp(path) for path in paths):
                self._entries[key] = snapshot.generation, paths, stamps, result
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    self._entries.popitem(last=False)
            return result
