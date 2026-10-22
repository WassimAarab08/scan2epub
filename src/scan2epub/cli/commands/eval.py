"""The ``scan2epub eval`` command.

It measures how well an engine recognises a book, by comparing its output
with the reference transcription of the corpus.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from scan2epub.application.cache import FileCache
from scan2epub.application.factory import build_ocr_engine
from scan2epub.config import load_config
from scan2epub.errors import ConfigurationError
from scan2epub.eval.runner import (
    SampleResult,
    evaluate_sample,
    render_markdown,
    sample_directories,
)

__all__ = ["eval"]


def eval(
    samples: Annotated[
        Path,
        typer.Option("--samples", help="The directory that holds the corpus."),
    ] = Path("samples"),
    ocr: Annotated[
        list[str] | None,
        typer.Option("--ocr", help="The engine to evaluate. May be repeated."),
    ] = None,
    markdown: Annotated[
        Path | None,
        typer.Option("--markdown", help="Write the table to this file."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the results as JSON.")] = False,
    config_file: Annotated[
        Path | None, typer.Option("--config", help="The configuration file.")
    ] = None,
) -> None:
    """Measure the CER and the WER of the OCR engines over the corpus."""
    console = Console()
    config = load_config(config_file)
    directories = sample_directories(samples)
    if not directories:
        raise ConfigurationError(
            f"There is no sample in {samples}. "
            "Run `uv run python scripts/fetch_samples.py` to build the corpus."
        )

    engines = list(ocr or [config.general.ocr_engine])
    cache = FileCache(config.cache_directory / "eval")
    results: list[SampleResult] = []
    for engine_name in engines:
        engine = build_ocr_engine(config, engine_name)
        for directory in directories:
            console.print(f"[dim]Evaluating {engine_name} on {directory.name}…[/dim]")
            results.append(
                evaluate_sample(
                    directory,
                    engine,
                    work_dir=config.cache_directory / "eval" / engine_name,
                    cache=cache,
                )
            )

    table = render_markdown(results)
    if markdown is not None:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(table, encoding="utf-8")
        console.print(f"[green]Written:[/green] {markdown}")

    if as_json:
        console.print_json(
            data=[
                {
                    "engine": result.engine,
                    "sample": result.sample,
                    "cer": result.cer,
                    "wer": result.wer,
                    "pages": result.pages,
                    "seconds_per_page": result.seconds_per_page,
                }
                for result in results
            ]
        )
        return

    grid = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    for column in ("Book", "Engine", "CER ↓", "WER ↓", "Pages", "s/page"):
        grid.add_column(column)
    for result in sorted(results, key=lambda item: (item.sample, item.engine)):
        grid.add_row(
            result.sample,
            result.engine,
            f"{result.cer:.4f}",
            f"{result.wer:.4f}",
            str(result.pages),
            f"{result.seconds_per_page:.2f}",
        )
    console.print()
    console.print(grid)
    console.print()
    console.print(json.dumps({"samples": len(directories), "engines": len(engines)}))
