"""The ``scan2epub estimate`` command.

It says what a run would cost **before** the run happens. Nothing is sent to
any provider: the estimate only counts the tokens of the pages and applies
the price of the model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from scan2epub.config import load_config
from scan2epub.errors import ConfigurationError
from scan2epub.infrastructure.llm.cost import estimate_cost
from scan2epub.infrastructure.pdf.pdfium_source import PdfiumPageSource
from scan2epub.logging import get_logger

__all__ = ["estimate"]

_LOGGER = get_logger(__name__)

#: The number of tokens that the answer of the corrector takes for one page
#: of a book.
OUTPUT_TOKENS_PER_PAGE = 1200

#: The number of tokens of the image of a page, for a vision model.
IMAGE_TOKENS_PER_PAGE = 1500


def estimate(
    source: Annotated[
        Path,
        typer.Argument(..., help="The PDF to estimate."),
    ],
    ocr: Annotated[
        str | None,
        typer.Option("--ocr", help="The OCR engine, for instance litellm/gpt-4o-mini."),
    ] = None,
    llm: Annotated[
        str | None,
        typer.Option("--llm", help="The corrector, for instance litellm/gpt-4o-mini."),
    ] = None,
    dpi: Annotated[int, typer.Option("--dpi", min=72, max=1200, help="The resolution.")] = 300,
    config_file: Annotated[
        Path | None, typer.Option("--config", help="The configuration file.")
    ] = None,
) -> None:
    """Estimate the cost of a run, without calling anything."""
    console = Console()
    load_config(config_file)

    if not source.is_file():
        raise ConfigurationError(f"The file {source} does not exist.")

    pages = PdfiumPageSource(source, dpi=dpi).page_count()
    console.print(f"[bold]The book[/bold] {source.name} has {pages} pages.")
    console.print()

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    for column in ("Model", "Role", "Input tokens", "Output tokens", "Cost"):
        table.add_column(column)

    total = 0.0
    notes: list[str] = []

    if ocr and "/" in ocr:
        input_tokens = pages * IMAGE_TOKENS_PER_PAGE
        output_tokens = pages * 900
        input_cost, output_cost, note = estimate_cost(ocr, input_tokens, output_tokens)
        total += input_cost + output_cost
        table.add_row(
            ocr,
            "OCR",
            f"{input_tokens:,}",
            f"{output_tokens:,}",
            f"${input_cost + output_cost:.4f}",
        )
        if note:
            notes.append(note)
    elif ocr:
        table.add_row(ocr, "OCR", "-", "-", "local, no cost")

    if llm and "/" in llm:
        input_tokens = pages * 2000
        output_tokens = pages * OUTPUT_TOKENS_PER_PAGE
        input_cost, output_cost, note = estimate_cost(llm, input_tokens, output_tokens)
        total += input_cost + output_cost
        table.add_row(
            llm,
            "correction",
            f"{input_tokens:,}",
            f"{output_tokens:,}",
            f"${input_cost + output_cost:.4f}",
        )
        if note:
            notes.append(note)
    elif llm:
        table.add_row(llm, "correction", "-", "-", "local, no cost")

    console.print(table)
    console.print()
    console.print(f"[bold]The estimated cost is ${total:.4f}.[/bold]")
    console.print(
        "[dim]It is an upper bound: it assumes that every page costs the most it can cost.[/dim]"
    )
    for note in notes:
        console.print(f"[yellow]note:[/yellow] {note}")
    console.print()
    console.print(
        "Set [bold]max_cost_usd[/bold] in the configuration to stop a run that "
        "goes over the budget."
    )
    _LOGGER.info("estimate.done", pages=pages, cost=total)
