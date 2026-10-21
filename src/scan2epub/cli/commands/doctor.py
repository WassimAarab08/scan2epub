"""The ``scan2epub doctor`` command.

``doctor`` reports what the installation can actually do. It never prints
credentials: the API keys are only reported as present or absent.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.table import Table

from scan2epub import __version__
from scan2epub.application.stages.validate import find_epubcheck
from scan2epub.config import default_config_path, load_config

__all__ = ["doctor"]

#: The environment variables that hold the credentials of the remote engines.
API_KEY_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "OPENROUTER_API_KEY",
)

#: The distributions whose version is interesting.
DISTRIBUTIONS = {
    "pypdfium2": "pypdfium2",
    "opencv": "opencv-python-headless",
    "numpy": "numpy",
    "pillow": "pillow",
    "pytesseract": "pytesseract",
    "pydantic": "pydantic",
    "typer": "typer",
    "fastapi": "fastapi",
    "litellm": "litellm",
}


def _tesseract_report() -> dict[str, object]:
    """Return the state of the Tesseract installation."""
    from scan2epub.infrastructure.ocr.tesseract import (  # noqa: PLC0415
        available_languages,
        tesseract_version,
    )

    installed = tesseract_version()
    return {
        "available": installed is not None,
        "version": installed,
        "languages": available_languages(),
    }


def _dependency_versions() -> dict[str, str]:
    """Return the versions of the main runtime dependencies."""
    versions: dict[str, str] = {}
    for label, distribution in DISTRIBUTIONS.items():
        try:
            versions[label] = version(distribution)
        except PackageNotFoundError:
            versions[label] = "not installed"
    return versions


def _api_key_report() -> dict[str, bool]:
    """Report which API keys are present, without revealing them."""
    return {name: bool(os.environ.get(name)) for name in API_KEY_NAMES}


def default_cache_dir() -> Path:
    """Return the default artefact cache directory."""
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "scan2epub"


def doctor(
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
) -> None:
    """Show what the current installation supports."""
    console = Console()
    config = load_config()
    tesseract = _tesseract_report()
    dependencies = _dependency_versions()
    api_keys = _api_key_report()

    report: dict[str, object] = {
        "scan2epub": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "config_file": str(config.source_path) if config.source_path else None,
        "default_config_file": str(default_config_path()),
        "cache_dir": str(default_cache_dir()),
        "dependencies": dependencies,
        "tesseract": tesseract,
        "epubcheck": str(find_epubcheck() or "not found"),
        "api_keys_present": api_keys,
        "ocr_engines": ["tesseract"],
    }

    if as_json:
        console.print_json(json.dumps(report, default=str))
        return

    console.print(f"[bold]scan2epub[/bold] {__version__}")
    console.print(f"  Python      {report['python']}")
    console.print(f"  Platform    {report['platform']}")
    console.print(f"  Config      {report['config_file'] or 'not found (using defaults)'}")

    console.print()
    console.print("[bold]OCR engines[/bold]")
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Engine")
    table.add_column("Status")
    table.add_column("Details")
    if tesseract["available"]:
        languages = cast("list[str]", tesseract["languages"])
        table.add_row(
            "tesseract",
            "[green]available[/green]",
            f"version {tesseract['version']}, languages: {', '.join(languages) or 'none'}",
        )
    else:
        table.add_row("tesseract", "[red]not found[/red]", "install it and add it to PATH")
    console.print(table)

    console.print()
    console.print("[bold]Dependencies[/bold]")
    for name, installed in dependencies.items():
        console.print(f"  {name:<12} {installed}")

    console.print()
    console.print("[bold]Validation[/bold]")
    console.print(f"  EPUBCheck   {report['epubcheck']}")

    console.print()
    console.print("[bold]API keys[/bold] (presence only, never the value)")
    for name, present in api_keys.items():
        marker = "[green]set[/green]" if present else "[dim]not set[/dim]"
        console.print(f"  {name:<22} {marker}")
