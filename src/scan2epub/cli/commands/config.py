"""The ``scan2epub config`` command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.syntax import Syntax

from scan2epub.config import default_config_path, load_config

__all__ = ["config"]

#: The template that ``scan2epub config init`` writes.
TEMPLATE = """\
# The configuration of scan2epub.
#
# Every value can also be set with an environment variable prefixed with
# SCAN2EPUB_, and the most common ones can be given on the command line.
# The file is optional: without it the defaults are used.

[general]
# The resolution of the rendered pages.
dpi = 300
# The default language of the OCR engine and of the generated book.
language = "spa"
# The OCR engine to use by default.
ocr_engine = "tesseract"
# The text corrector to use by default. Leave it out to stay offline.
# text_corrector = "litellm/ollama/qwen3"
# Modernise the spelling of the text. Off by default: the original spelling
# of the book is preserved.
modernize = false
# The metadata of the book. Every field can be overridden on the command line.
# title = "Historia de la imprenta en Espana"
# author = "Anonimo"
# year = "1765"
# Validate the generated EPUB with EPUBCheck.
validate_epub = true

[preprocess]
deskew = true
max_skew_degrees = 5.0
binarize = true
denoise = true
crop_borders = true
crop_margin = 16
binary_block_size = 31
binary_c = 12

[clean]
# The height of the header and of the footer zones, as a fraction of the page.
header_zone = 0.12
footer_zone = 0.12
# The zone where the footnotes live.
footnote_zone = 0.82
# How many pages a block must repeat on to be considered a running head.
min_running_head_repeats = 3
max_running_head_chars = 90
join_hyphens = true
normalize_characters = true
join_paragraphs = true
detect_footnotes = true

[ocr.tesseract]
# The language of the OCR. Use "spa_old" for the books printed before 1900,
# and combine them: "spa+spa_old+eng".
lang = "spa"
# The OCR engine mode and the page segmentation mode of Tesseract.
oem = 1
psm = 3
# The directory that holds the "*.traineddata" files. When it is not set,
# the TESSDATA_PREFIX environment variable is used.
# tessdata_dir = "/opt/tessdata"

# A third-party engine is registered here. The adapter is an import path in
# the form "module:Class".
#
# [ocr.my-engine]
# adapter = "my_package.my_module:MyEngine"
#
# [ocr.my-engine.options]
# model = "my-model"
"""


def config(
    init: Annotated[
        bool,
        typer.Option("--init", help="Write a documented configuration file."),
    ] = False,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Where the file is written or read."),
    ] = None,
    show: Annotated[
        bool,
        typer.Option("--show", help="Print the effective configuration."),
    ] = False,
) -> None:
    """Write or show the configuration file."""
    console = Console()
    target = path or default_config_path()

    if init:
        if target.exists():
            typer.secho(f"{target} already exists; it was not overwritten.", fg=typer.colors.YELLOW)
            raise typer.Exit(1)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(TEMPLATE, encoding="utf-8")
        console.print(f"[green]Written:[/green] {target}")
        console.print("Edit it and run [bold]scan2epub doctor[/bold] to check it.")
        return

    if show:
        effective = load_config(target if target.is_file() else None)
        payload: dict[str, object] = {
            "general": effective.general.model_dump(),
            "preprocess": effective.preprocess.model_dump(),
            "clean": effective.clean.model_dump(),
            "ocr": {name: provider.model_dump() for name, provider in effective.ocr.items()},
            "correctors": {
                name: provider.model_dump() for name, provider in effective.correctors.items()
            },
            "source_path": str(effective.source_path) if effective.source_path else None,
        }
        console.print(
            Syntax(
                json.dumps(payload, indent=2, default=str),
                "json",
                theme="ansi_dark",
                background_color="default",
            )
        )
        return

    console.print(f"[bold]Configuration file:[/bold] {target}")
    console.print(f"  exists:  {target.is_file()}")
    effective = load_config(target if target.is_file() else None)
    console.print(f"  used:    {effective.source_path or 'the defaults'}")
    console.print(f"  engine:  {effective.general.ocr_engine}")
    console.print(f"  language:{effective.general.language}")
    console.print("")
    console.print("Write a documented template with [bold]scan2epub config --init[/bold].")
