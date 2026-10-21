"""Tests for the artefact cache."""

from __future__ import annotations

from pathlib import Path

import pytest

from scan2epub.application.cache import FileCache, hash_bytes, hash_file, hash_json


def test_an_artefact_is_stored_and_read_back(tmp_path: Path) -> None:
    """The cache behaves like a key-value store."""
    cache = FileCache(tmp_path / "cache")
    cache.put("abcdef123456", b"payload")
    assert cache.get("abcdef123456") == b"payload"
    assert cache.has("abcdef123456")


def test_a_missing_artefact_returns_none(tmp_path: Path) -> None:
    """A cache miss is not an error."""
    cache = FileCache(tmp_path / "cache")
    assert cache.get("abcdef123456") is None
    assert not cache.has("abcdef123456")


def test_json_artefacts_round_trip(tmp_path: Path) -> None:
    """JSON payloads are stored and read back."""
    cache = FileCache(tmp_path / "cache")
    cache.put_json("abcdef123456", {"a": [1, 2, 3], "b": "ñ"})
    assert cache.get_json("abcdef123456") == {"a": [1, 2, 3], "b": "ñ"}


def test_an_invalid_key_is_rejected(tmp_path: Path) -> None:
    """A key that is too short cannot address a file."""
    cache = FileCache(tmp_path / "cache")
    with pytest.raises(ValueError):
        cache.path_for("ab")


def test_a_file_can_be_copied_into_the_cache(tmp_path: Path) -> None:
    """A file is stored byte for byte."""
    source = tmp_path / "artefact.bin"
    source.write_bytes(b"binary")
    cache = FileCache(tmp_path / "cache")
    cache.put_file("abcdef123456", source)
    assert cache.get("abcdef123456") == b"binary"


def test_the_cache_can_be_cleared(tmp_path: Path) -> None:
    """Clearing the cache removes every artefact."""
    cache = FileCache(tmp_path / "cache")
    cache.put("abcdef123456", b"payload")
    cache.clear()
    assert cache.get("abcdef123456") is None


def test_the_hashes_are_stable() -> None:
    """The same input always produces the same hash."""
    assert hash_bytes(b"abc") == hash_bytes(b"abc")
    assert hash_bytes(b"abc") != hash_bytes(b"abd")
    assert hash_json({"a": 1, "b": 2}) == hash_json({"b": 2, "a": 1})
    assert hash_json({"a": 1}) != hash_json({"a": 2})


def test_a_file_hash_is_computed(tmp_path: Path) -> None:
    """A file is hashed by its content."""
    path = tmp_path / "file.bin"
    path.write_bytes(b"content")
    assert hash_file(path) == hash_bytes(b"content")
