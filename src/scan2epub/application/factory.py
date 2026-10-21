"""Factories that assemble the pipeline from a configuration.

Both the command line and the REST API build the very same pipeline. Keeping
the wiring in one place means that a new engine is registered once and works
everywhere.
"""

from __future__ import annotations

from pathlib import Path

from scan2epub.application.cache import FileCache
from scan2epub.application.pipeline import Pipeline
from scan2epub.application.progress import ProgressReporter
from scan2epub.config import Config
from scan2epub.domain.ports import OcrEngine
from scan2epub.errors import ConfigurationError
from scan2epub.infrastructure.imaging.opencv_preprocessor import OpenCvPreprocessor
from scan2epub.infrastructure.ocr.tesseract import TesseractOcrEngine
from scan2epub.infrastructure.pdf.pdfium_source import PdfiumPageSource
from scan2epub.logging import get_logger

__all__ = [
    "available_engines",
    "build_ocr_engine",
    "build_pipeline",
    "with_language",
]

_LOGGER = get_logger(__name__)

#: The OCR engines that ship with the project.
KNOWN_ENGINES = ("tesseract",)


def available_engines() -> tuple[str, ...]:
    """Return the names of the OCR engines that can be used."""
    return KNOWN_ENGINES


def build_ocr_engine(config: Config, name: str | None = None) -> OcrEngine:
    """Build the OCR engine described by the configuration.

    Args:
        config: The effective configuration.
        name: The name of the engine. Defaults to ``[general] ocr_engine``.

    Returns:
        The engine.

    Raises:
        ConfigurationError: If the engine is unknown or not installed.
    """
    engine_name = name or config.general.ocr_engine
    if engine_name != "tesseract":
        raise ConfigurationError(
            f"Unknown OCR engine {engine_name!r}. Available engines: {', '.join(KNOWN_ENGINES)}."
        )

    provider = config.ocr_provider(engine_name)
    options = provider.options
    tessdata = options.get("tessdata_dir")
    language = str(options.get("lang", config.general.language))
    return TesseractOcrEngine(
        lang=language,
        oem=int(options.get("oem", 1)),
        psm=int(options.get("psm", 3)),
        tessdata_dir=Path(tessdata) if tessdata else None,
    )


def with_language(config: Config, language: str) -> Config:
    """Return a copy of the configuration that uses another OCR language."""
    return Config(
        general=config.general.model_copy(update={"language": language}),
        preprocess=config.preprocess,
        clean=config.clean,
        ocr=config.ocr,
        correctors=config.correctors,
        source_path=config.source_path,
    )


def build_pipeline(
    config: Config,
    source_path: Path,
    work_dir: Path,
    *,
    cache_dir: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> Pipeline:
    """Build a pipeline for a source document.

    Args:
        config: The effective configuration.
        source_path: The PDF to convert.
        work_dir: Where the intermediate files are written.
        cache_dir: Where the artefacts are cached. When omitted, the cache is
            disabled.
        reporter: An optional progress reporter.

    Returns:
        The pipeline.
    """
    cache = FileCache(cache_dir) if cache_dir is not None else None
    engine = build_ocr_engine(config)
    _LOGGER.debug("pipeline.built", engine=engine.name, source=str(source_path))
    return Pipeline(
        source=PdfiumPageSource(source_path, dpi=config.general.dpi),
        preprocessor=OpenCvPreprocessor(config.preprocess),
        ocr=engine,
        config=config,
        work_dir=work_dir,
        cache=cache,
        reporter=reporter,
    )
