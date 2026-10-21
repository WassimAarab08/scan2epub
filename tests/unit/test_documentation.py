"""Tests that keep the documentation honest.

A broken link in the README is a small bug, but a small bug that nobody
notices. These tests walk every Markdown file of the repository and check
that the relative links point at something that exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

#: The Markdown files that are checked.
MARKDOWN = ("*.md", "docs/*.md", "samples/*.md", ".github/*.md")

#: A link to a file or a directory, possibly with an anchor.
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

#: A link that points outside the repository.
_EXTERNAL = re.compile(r"^(?:https?:|mailto:|#|data:)")


def _markdown_files(root: Path) -> list[Path]:
    """Return every Markdown file of the repository."""
    files: list[Path] = []
    for pattern in MARKDOWN:
        files.extend(root.glob(pattern))
    return sorted(set(files))


def _links(path: Path) -> list[str]:
    """Return the relative links of a Markdown file."""
    text = path.read_text(encoding="utf-8")
    return [
        match.group(1) for match in _LINK_RE.finditer(text) if not _EXTERNAL.match(match.group(1))
    ]


@pytest.mark.parametrize("pattern", MARKDOWN)
def test_the_relative_links_resolve(project_root: Path, pattern: str) -> None:
    """Every relative link points at a file that exists."""
    broken: list[str] = []
    for path in _markdown_files(project_root):
        if not path.match(pattern):
            continue
        for link in _links(path):
            target = link.split("#", 1)[0]
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"{path.relative_to(project_root)} -> {link}")
    assert not broken, "broken links:\n" + "\n".join(broken)


def test_every_documented_file_exists(project_root: Path) -> None:
    """The documents that the README links to are all there."""
    expected = [
        "docs/architecture.md",
        "docs/adding-an-engine.md",
        "docs/configuration.md",
        "docs/usage.md",
        "docs/testing.md",
        "docs/epub-layout.md",
        "docs/benchmarks.md",
        "docs/naming.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "CHANGELOG.md",
        "THIRD_PARTY_LICENSES.md",
        "LICENSE",
        "NOTICE",
        "README.md",
        "README.es.md",
    ]
    missing = [name for name in expected if not (project_root / name).is_file()]
    assert not missing, f"missing documents: {missing}"


def test_the_readmes_document_the_same_commands(project_root: Path) -> None:
    """The English and the Spanish README mention the same commands."""
    english = (project_root / "README.md").read_text(encoding="utf-8")
    spanish = (project_root / "README.es.md").read_text(encoding="utf-8")
    for command in ("scan2epub convert", "scan2epub doctor", "scan2epub serve"):
        assert command in english
        assert command in spanish


def test_the_licence_is_apache(project_root: Path) -> None:
    """The licence of the project is the Apache 2.0."""
    licence = (project_root / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in licence
    assert "Version 2.0" in licence


def test_the_third_party_licences_reject_the_copyleft_libraries(project_root: Path) -> None:
    """The rejected libraries are listed in the documentation."""
    document = (project_root / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    for name in ("PyMuPDF", "EbookLib", "marker", "MinerU"):
        assert name in document
    assert "AGPL" in document
