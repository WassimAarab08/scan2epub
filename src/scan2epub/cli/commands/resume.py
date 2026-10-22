"""The ``scan2epub resume`` command.

It continues an interrupted conversion: the pages that were already
recognised come from the cache, and the report says how much of the work was
saved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from scan2epub.application.cache import FileCache
from scan2epub.application.factory import build_corrector, build_ocr_engine, with_language
from scan2epub.application.pipeline import Pipeline
from scan2epub.application.progress import ProgressEvent
from scan2epub.config import load_config
from scan2epub.domain.models import BookMetadata
from scan2epub.errors import ConfigurationError
from scan2epub.infrastructure.imaging.opencv_preprocessor import OpenCvPreprocessor
from scan2epub.infrastructure.pdf.pdfium_source import PdfiumPageSource
from scan2epub.logging import get_logger

__all__ = ["resume"]

_LOGGER = get_logger(__name__)


def resume(
    source: Annotated[
        Path,
        typer.Argument(..., help="The PDF to convert."),
    ],
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="The destination .epub file."),
    ] = None,
    language: Annotated[
        str | None,
        typer.Option("--lang", help="The language of the OCR engine."),
    ] = None,
    cache_dir: Annotated[
        Path | None,
        typer.Option("--cache-dir", help="Where the artefacts are cached."),
    ] = None,
    config_file: Annotated[
        Path | None, typer.Option("--config", help="The configuration file.")
    ] = None,
) -> None:
    """Continue an interrupted conversion, reusing the cache."""
    console = Console()
    config = load_config(config_file)
    if not source.is_file():
        raise ConfigurationError(f"The file {source} does not exist.")
    if language:
        config = with_language(config, language)

    destination = output or source.with_suffix(".epub")
    root = cache_dir or config.cache_directory
    cache = FileCache(root / "cache")
    work = root / "work" / source.stem

    pipeline = Pipeline(
        source=PdfiumPageSource(source, dpi=config.general.dpi),
        preprocessor=OpenCvPreprocessor(config.preprocess),
        ocr=build_ocr_engine(config),
        corrector=build_corrector(config),
        config=config,
        work_dir=work,
        cache=cache,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("Resuming", total=None)

        def report(event: ProgressEvent) -> None:
            if event.page is not None and event.total:
                progress.update(task_id, completed=event.page, total=event.total)
            elif event.total:
                progress.update(task_id, completed=event.total, total=event.total)

        pipeline.reporter = report
        result = pipeline.run(
            BookMetadata(
                title=config.general.title or "",
                author=config.general.author or "",
                language=config.general.output_language or config.general.language,
                year=config.general.year,
            ),
            destination,
        )
        progress.update(task_id, description="Done", completed=1, total=1)

    console.print()
    console.print(f"[bold green]EPUB written:[/bold green] {result.epub_path}")
    console.print(f"  pages               {result.page_count}")
    console.print(f"  pages recognised    {result.pages_recognised}")
    console.print(f"  pages from the cache {result.pages_from_cache}")
    if result.corrections_rejected:
        console.print(
            f"  corrections rejected {result.corrections_rejected}"
            " (the guardrail kept the original)"
        )
    console.print(f"  duration            {result.duration_seconds:.1f} s")
