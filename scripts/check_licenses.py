#!/usr/bin/env python
"""Fail the build when a copyleft dependency sneaks in.

The project is Apache-2.0 licensed and must stay usable inside proprietary
products, so every dependency — direct or transitive — has to be permissive.
This script reads the metadata of the installed distributions and fails when
one of them declares a copyleft or proprietary license.

Usage::

    uv run python scripts/check_licenses.py
    uv run python scripts/check_licenses.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from importlib.metadata import distributions

#: The license identifiers that are *not* allowed.
FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bAGPL\b", re.IGNORECASE),
    re.compile(r"\bGPL\b", re.IGNORECASE),
    re.compile(r"\bLGPL\b", re.IGNORECASE),
    re.compile(r"\bSSPL\b", re.IGNORECASE),
    re.compile(r"\bBUSL\b", re.IGNORECASE),
    re.compile(r"\bCDDL\b", re.IGNORECASE),
    re.compile(r"\bEPL\b", re.IGNORECASE),
    re.compile(r"commercial", re.IGNORECASE),
    re.compile(r"proprietary", re.IGNORECASE),
    re.compile(r"non-?commercial", re.IGNORECASE),
    re.compile(r"commons clause", re.IGNORECASE),
)

#: Licenses that are allowed but deserve a note in THIRD_PARTY_LICENSES.md.
#: MPL-2.0 is a file-level copyleft: it does not affect the licensing of the
#: work that merely uses the package.
ALLOWED_PATTERNS: tuple[re.Pattern[str], ...] = (re.compile(r"\bMPL\b", re.IGNORECASE),)

#: The distributions that are known to be copyleft. They are listed here so
#: that the error message is explicit when somebody adds one of them.
KNOWN_REJECTED: dict[str, str] = {
    "pymupdf": "AGPL-3.0",
    "fitz": "AGPL-3.0",
    "ebooklib": "AGPL-3.0",
    "marker": "GPL-3.0",
    "surya": "GPL-3.0",
    "mineru": "AGPL-3.0 / non-commercial",
    "kraken-paddle": "GPL-3.0",
}

#: The dependencies of the project itself are allowed to be anything
#: permissive, but the packages that are known to pull copyleft code in are
#: checked explicitly.
ALLOWED_EXCEPTIONS: frozenset[str] = frozenset(
    {
        # ``tornado`` is pulled in by the Jupyter stack and is BSD licensed.
        "tornado",
    }
)


def _license_text(distribution: object) -> str:
    """Return the license declared by a distribution.

    Only the short metadata is used. The full text of the licenses that the
    wheels bundle (the GCC runtime of NumPy, for instance) is ignored: those
    exceptions explicitly allow linking into a non-copyleft work.
    """
    metadata = getattr(distribution, "metadata", None)
    if metadata is None:
        return ""
    parts: list[str] = []
    expression = metadata.get("License-Expression") or ""
    if expression:
        parts.append(expression)
    for classifier in metadata.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            parts.append(classifier)
    declared = metadata.get("License") or ""
    if declared and declared != "UNKNOWN" and len(declared) < 200:
        parts.append(declared)
    return " | ".join(parts)


def _normalize(name: str) -> str:
    """Return the canonical name of a distribution."""
    return re.sub(r"[-_.]+", "-", name).lower()


def check() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return the offending and the noteworthy distributions."""
    problems: list[dict[str, str]] = []
    notable: list[dict[str, str]] = []
    seen: set[str] = set()
    for distribution in distributions():
        raw_name = getattr(distribution, "name", "") or ""
        name = _normalize(raw_name)
        if not name or name in seen:
            continue
        seen.add(name)
        if name in ALLOWED_EXCEPTIONS:
            continue
        if name in KNOWN_REJECTED:
            problems.append(
                {
                    "package": name,
                    "license": KNOWN_REJECTED[name],
                    "reason": "known copyleft dependency",
                }
            )
            continue
        license_text = _license_text(distribution)
        if not license_text:
            continue
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(license_text):
                problems.append(
                    {
                        "package": name,
                        "license": license_text,
                        "reason": f"matches {pattern.pattern}",
                    }
                )
                break
        else:
            for pattern in ALLOWED_PATTERNS:
                if pattern.search(license_text):
                    notable.append({"package": name, "license": license_text})
                    break
    return (
        sorted(problems, key=lambda item: item["package"]),
        sorted(notable, key=lambda item: item["package"]),
    )


def main() -> int:
    """Run the check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    arguments = parser.parse_args()

    problems, notable = check()
    if arguments.json:
        print(
            json.dumps(
                {"problems": problems, "notable": notable, "ok": not problems},
                indent=2,
            )
        )
    elif problems:
        print("Copyleft or proprietary dependencies found:\n", file=sys.stderr)
        for problem in problems:
            print(
                f"  {problem['package']}: {problem['license']} ({problem['reason']})",
                file=sys.stderr,
            )
        print(
            "\nscan2epub is Apache-2.0 licensed and only uses permissive dependencies.",
            file=sys.stderr,
        )
    else:
        print("All the installed dependencies use permissive licenses.")
        for item in notable:
            print(f"  note: {item['package']} uses {item['license']}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
