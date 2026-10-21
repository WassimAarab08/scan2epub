#!/usr/bin/env python
"""Fetch the JavaScript assets needed by the browser tests.

The tests that open the generated EPUB in a real reader need `foliate-js`,
the reference EPUB 3 renderer. It is fetched from npm and pinned to the
version that the project depends on, so the test suite stays reproducible.

Usage::

    uv run python scripts/fetch_browser_assets.py
"""

from __future__ import annotations

import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tests" / "browser" / "assets" / "foliate-js"

#: The version of foliate-js that the project depends on.
FOLIATE_VERSION = "1.0.1"

#: The directories of the npm package that are not needed by the tests.
EXCLUDED = ("package/tests/", "package/.github/", "package/rollup/", "package/node_modules/")


def _download() -> Path:
    """Download the npm tarball of foliate-js and return its path."""
    import urllib.request

    url = f"https://registry.npmjs.org/foliate-js/-/foliate-js-{FOLIATE_VERSION}.tgz"
    target = ROOT / "tmp" / f"foliate-js-{FOLIATE_VERSION}.tgz"
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as response:
        target.write_bytes(response.read())
    return target


def main() -> int:
    """Fetch and unpack the assets."""
    if TARGET.is_dir() and (TARGET / "reader.html").is_file():
        print(f"foliate-js {FOLIATE_VERSION} is already installed in {TARGET}")
        return 0

    tarball = _download()
    TARGET.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            name = member.name
            if any(name.startswith(prefix) for prefix in EXCLUDED):
                continue
            if name.endswith(("eslint.config.js", "rollup.config.js")):
                continue
            relative = name[len("package/") :] if name.startswith("package/") else name
            if not relative:
                continue
            destination = TARGET / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            destination.write_bytes(extracted.read())
    print(f"foliate-js {FOLIATE_VERSION} installed in {TARGET}")
    missing = [
        name
        for name in ("reader.html", "reader.js", "epub.js", "vendor/zip.js")
        if not (TARGET / name).is_file()
    ]
    if missing:
        print(f"warning: {len(missing)} files are missing: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
