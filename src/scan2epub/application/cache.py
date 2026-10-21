"""A small content-addressed cache backed by the filesystem.

The cache is what makes a long job resumable: every stage artefact is stored
under a key derived from the hash of its inputs, so re-running a job reuses
everything that has not changed.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

__all__ = ["FileCache", "hash_bytes", "hash_file", "hash_json"]


def hash_bytes(data: bytes) -> str:
    """Return the hexadecimal SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    """Return the hexadecimal SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_json(payload: object) -> str:
    """Return a stable hash of a JSON-serialisable payload."""
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class FileCache:
    """Store artefacts on disk, addressed by a hexadecimal key."""

    def __init__(self, root: Path) -> None:
        """Initialise the cache.

        Args:
            root: The directory that holds the cached artefacts.
        """
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        """Return the path of the artefact stored under ``key``."""
        safe = "".join(char for char in key if char.isalnum())
        if len(safe) < 4:
            raise ValueError(f"Invalid cache key: {key!r}")
        return self.root / safe[:2] / safe[2:4] / safe

    def has(self, key: str) -> bool:
        """Whether an artefact is stored under ``key``."""
        return self.path_for(key).is_file()

    def get(self, key: str) -> bytes | None:
        """Return the artefact stored under ``key``, or ``None``."""
        path = self.path_for(key)
        if not path.is_file():
            return None
        return path.read_bytes()

    def put(self, key: str, data: bytes) -> None:
        """Store ``data`` under ``key``."""
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary file first so that a crash never leaves a
        # truncated artefact behind.
        handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        temporary_path = Path(temporary)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
            temporary_path.replace(path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    def put_file(self, key: str, source: Path) -> None:
        """Store the content of ``source`` under ``key``."""
        self.put(key, source.read_bytes())

    def get_json(self, key: str) -> object | None:
        """Return the JSON artefact stored under ``key``, or ``None``."""
        raw = self.get(key)
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8"))

    def put_json(self, key: str, payload: object) -> None:
        """Store a JSON-serialisable payload under ``key``."""
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.put(key, encoded)

    def clear(self) -> None:
        """Remove every cached artefact."""
        if self.root.exists():
            for path in sorted(self.root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
