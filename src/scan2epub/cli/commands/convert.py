"""The ``scan2epub convert`` command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn

from scan2epub.application.cache import FileCache
from scan2epub.application.pipeline import Pipeline, PipelineResult
from scan2epub.application.progress import ProgressEvent
from scan2epub.config import Config, GeneralConfig, load_config, output_language_for
from scan2epub.domain.models import BookMetadata
from scan2epub.errors import ConfigurationError
from scan2epub.infrastructure.imaging.opencv_preprocessor import OpenCvPreprocessor
from scan2epub.infrastructure.ocr.tesseract import TesseractOcrEngine
from scan2epub.infrastructure.pdf.pdfium_source import PdfiumPageSource
from scan2epub.logging import get_logger

__all__ = ["convert"]

_LOGGER = get_logger(__name__)

_STAGE_LABELS = {
    "ingest": "Rendering the pages",
    "preprocess": "Cleaning up the images",
    "ocr": "Recognising the text",
    "clean": "Cleaning the text",
    "correct": "Correcting the text",
    "structure": "Detecting the chapters",
    "epub": "Writing the EPUB",
    "validate": "Validating the EPUB",
}


class _ConsoleReporter:
    """Forward the pipeline progress to a Rich progress bar."""

    def __init__(self, progress: Progress, task_id: TaskID) -> None:
        self._progress = progress
        self._task_id = task_id
        self._stage = "ingest"

    def __call__(self, event: ProgressEvent) -> None:
        """Update the progress bar."""
        if event.stage != self._stage:
            self._stage = event.stage
            self._progress.update(
                self._task_id, description=_STAGE_LABELS.get(event.stage, event.stage)
            )
        if event.page is not None and event.total:
            self._progress.update(self._task_id, completed=event.page, total=event.total)
        elif event.total:
            self._progress.update(self._task_id, completed=event.total, total=event.total)


def _build_metadata(
    source: Path,
    general: GeneralConfig,
    title: str | None,
    author: str | None,
    year: str | None,
    ocr_language: str,
) -> BookMetadata:
    """Derive the book metadata from the file name and the options."""
    resolved_title = (
        title or general.title or source.stem.replace("_", " ").replace("-", " ").strip()
    )
    resolved_title = resolved_title or "Libro sin título"
    language = general.output_language or output_language_for(ocr_language, general.language)
    return BookMetadata(
        title=resolved_title,
        author=author or general.author or "",
        language=language,
        year=year or general.year,
        identifier="",
    )


def _resolve_paths(
    work_dir: Path | None, cache_dir: Path | None, source: Path
) -> tuple[Path, Path]:
    """Return the work directory and the cache directory."""
    base_work = work_dir or source.with_suffix(".scan2epub")
    base_cache = cache_dir or base_work / "cache"
    return base_work, base_cache


def convert(
    source: Annotated[
        Path,
        typer.Argument(
            ...,
            help="The scanned PDF to convert.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="The destination .epub file."),
    ] = None,
    ocr: Annotated[
        str,
        typer.Option("--ocr", help="The OCR engine to use (tesseract)."),
    ] = "tesseract",
    language: Annotated[
        str | None,
        typer.Option("--lang", help="Tesseract language, e.g. spa, spa_old, eng."),
    ] = None,
    dpi: Annotated[
        int | None,
        typer.Option("--dpi", min=72, max=1200, help="Resolution of the rendered pages."),
    ] = None,
    title: Annotated[str | None, typer.Option("--title", help="Title of the book.")] = None,
    author: Annotated[str | None, typer.Option("--author", help="Author of the book.")] = None,
    year: Annotated[str | None, typer.Option("--year", help="Year of publication.")] = None,
    output_language: Annotated[
        str | None,
        typer.Option("--output-language", help="Language of the generated EPUB."),
    ] = None,
    work_dir: Annotated[
        Path | None, typer.Option("--work-dir", help="Where the intermediate files are written.")
    ] = None,
    cache_dir: Annotated[
        Path | None, typer.Option("--cache-dir", help="Where the artefact cache is stored.")
    ] = None,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Disable the artefact cache.")
    ] = False,
    no_validate: Annotated[
        bool, typer.Option("--no-validate", help="Skip the EPUBCheck validation.")
    ] = False,
    config_file: Annotated[
        Path | None,
        typer.Option("--config", help="Path to a config.toml file."),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the result summary as JSON.")
    ] = False,
) -> None:
    """Convert a scanned PDF into a reflowable EPUB 3 file.

    The conversion is entirely local: no API key and no network access are
    needed for the default engine.
    """
    console = Console()
    config = load_config(config_file)
    config = _apply_overrides(
        config,
        language=language,
        dpi=dpi,
        title=title,
        author=author,
        year=year,
        output_language=output_language,
        ocr=ocr,
        validate_epub=not no_validate,
    )

    if config.general.ocr_engine != "tesseract":
        raise ConfigurationError(
            f"Unknown OCR engine {config.general.ocr_engine!r}. Available engines: tesseract."
        )

    destination = output or source.with_suffix(".epub")
    work, cache_root = _resolve_paths(work_dir, cache_dir, source)

    engine_config = config.ocr_provider("tesseract")
    options = engine_config.options
    tessdata = options.get("tessdata_dir")
    # The command line wins over the provider section, which wins over the
    # general configuration.
    ocr_language = language or str(options.get("lang", config.general.language))
    engine = TesseractOcrEngine(
        lang=ocr_language,
        oem=int(options.get("oem", 1)),
        psm=int(options.get("psm", 3)),
        tessdata_dir=Path(tessdata) if tessdata else None,
    )
    metadata = _build_metadata(source, config.general, title, author, year, ocr_language)

    cache = None if no_cache else FileCache(cache_root)
    pipeline = Pipeline(
        source=PdfiumPageSource(source, dpi=config.general.dpi),
        preprocessor=OpenCvPreprocessor(config.preprocess),
        ocr=engine,
        config=config,
        work_dir=work,
        cache=cache,
    )

    if as_json:
        result = pipeline.run(metadata, destination)
        _print_json(console, result)
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("Starting", total=None)
        pipeline.reporter = _ConsoleReporter(progress, task_id)
        result = pipeline.run(metadata, destination)
        progress.update(task_id, description="Done", completed=1, total=1)

    _print_summary(console, result)


def _apply_overrides(
    config: Config,
    *,
    language: str | None,
    dpi: int | None,
    title: str | None,
    author: str | None,
    year: str | None,
    output_language: str | None,
    ocr: str,
    validate_epub: bool,
) -> Config:
    """Return a copy of the configuration with the command line overrides applied."""
    general = config.general.model_copy(
        update={
            "language": language or config.general.language,
            "dpi": dpi or config.general.dpi,
            "title": title or config.general.title,
            "author": author or config.general.author,
            "year": year or config.general.year,
            "output_language": output_language or config.general.output_language,
            "ocr_engine": ocr,
            "validate_epub": validate_epub,
        }
    )
    return Config(
        general=general,
        preprocess=config.preprocess,
        clean=config.clean,
        ocr=config.ocr,
        correctors=config.correctors,
        source_path=config.source_path,
    )


def _print_summary(console: Console, result: PipelineResult) -> None:
    """Print a human readable summary of the conversion."""
    clean = result.clean
    console.print()
    console.print(f"[bold green]EPUB written:[/bold green] {result.epub_path}")
    console.print(f"  size        {result.epub_size / 1024:.1f} KiB")
    console.print(f"  pages       {result.page_count}")
    console.print(f"  chapters    {len(result.book.chapters)}")
    console.print(f"  duration    {result.duration_seconds:.1f} s")
    if clean.removed_running_heads:
        console.print(
            f"  removed running heads: {', '.join(clean.removed_running_heads[:5])}"
            f"{' …' if len(clean.removed_running_heads) > 5 else ''}"
        )
    console.print(f"  removed folios        {clean.removed_page_numbers}")
    console.print(f"  rejoined hyphenations  {clean.joined_hyphens}")
    console.print(f"  merged paragraphs      {clean.merged_paragraphs}")
    console.print(f"  footnotes detected     {clean.detected_footnotes}")

    validation = result.validation
    if not validation.ran:
        console.print(f"[yellow]  EPUBCheck skipped:[/yellow] {validation.reason}")
    elif validation.passed:
        console.print(
            f"[green]  EPUBCheck passed[/green] "
            f"({validation.warning_count} warnings, version {validation.version or 'unknown'})"
        )
        for warning in validation.warnings[:10]:
            console.print(f"    [yellow]warning:[/yellow] {warning}")
    else:
        console.print("[red]  EPUBCheck failed[/red]")
        for error in validation.errors[:20]:
            console.print(f"    [red]error:[/red] {error}")


def _print_json(console: Console, result: PipelineResult) -> None:
    """Print the result summary as JSON."""
    payload = {
        "epub": str(result.epub_path),
        "size": result.epub_size,
        "pages": result.page_count,
        "chapters": len(result.book.chapters),
        "duration_seconds": round(result.duration_seconds, 2),
        "removed_running_heads": list(result.clean.removed_running_heads),
        "removed_page_numbers": result.clean.removed_page_numbers,
        "joined_hyphens": result.clean.joined_hyphens,
        "merged_paragraphs": result.clean.merged_paragraphs,
        "footnotes": result.clean.detected_footnotes,
        "validation": {
            "ran": result.validation.ran,
            "passed": result.validation.passed,
            "errors": list(result.validation.errors),
            "warnings": list(result.validation.warnings),
            "version": result.validation.version,
            "reason": result.validation.reason,
        },
    }
    console.print_json(json.dumps(payload))
