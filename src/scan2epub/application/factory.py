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
from scan2epub.domain.ports import OcrEngine, TextCorrector
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
KNOWN_ENGINES = ("tesseract", "paddleocr-vl", "teleocr", "kraken")


def available_engines() -> tuple[str, ...]:
    """Return the names of the OCR engines that can be used."""
    return KNOWN_ENGINES


def build_ocr_engine(
    config: Config, name: str | None = None, *, language: str | None = None
) -> OcrEngine:
    """Build the OCR engine described by the configuration.

    Args:
        config: The effective configuration.
        name: The name of the engine. Defaults to ``[general] ocr_engine``.
        language: The language of the engine. When given, it wins over both
            the provider section and the general configuration.

    Returns:
        The engine.

    Raises:
        ConfigurationError: If the engine is unknown or not installed.
    """
    engine_name = name or config.general.ocr_engine
    provider = config.ocr_provider(engine_name)
    options = provider.options

    if engine_name == "tesseract":
        tessdata = options.get("tessdata_dir")
        engine_language = language or str(options.get("lang", config.general.language))
        return TesseractOcrEngine(
            lang=engine_language,
            oem=int(options.get("oem", 1)),
            psm=int(options.get("psm", 3)),
            tessdata_dir=Path(tessdata) if tessdata else None,
        )

    if engine_name == "paddleocr-vl":
        from scan2epub.infrastructure.ocr.paddleocr_vl import (  # noqa: PLC0415
            PaddleOcrVlEngine,
        )

        return PaddleOcrVlEngine(
            model=str(options.get("model", "PaddlePaddle/PaddleOCR-VL")),
            device=str(options.get("device", "auto")),
            max_new_tokens=int(options.get("max_new_tokens", 4096)),
            revision=options.get("revision"),
            trust_remote_code=bool(options.get("trust_remote_code", False)),
        )

    if engine_name == "teleocr":
        from scan2epub.infrastructure.ocr.teleocr import TeleOcrEngine  # noqa: PLC0415

        return TeleOcrEngine(
            model=str(options.get("model", "XingChen-AGI/TeleOCR")),
            device=str(options.get("device", "auto")),
            revision=str(options.get("revision", "true")),
            trust_remote_code=bool(options.get("trust_remote_code", False)),
            max_new_tokens=int(options.get("max_new_tokens", 4096)),
        )

    if engine_name == "kraken":
        from scan2epub.infrastructure.ocr.kraken import KrakenOcrEngine  # noqa: PLC0415

        return KrakenOcrEngine(
            model=str(options.get("model", "10.5281/zenodo.2577813")),
            binary=str(options.get("binary", "kraken")),
            timeout=int(options.get("timeout", 300)),
        )

    raise ConfigurationError(
        f"Unknown OCR engine {engine_name!r}. Available engines: {', '.join(KNOWN_ENGINES)}."
    )


def with_language(config: Config, language: str) -> Config:
    """Return a copy of the configuration that uses another OCR language.

    The provider section is updated as well, so that the engine and the
    cache key always agree with the language that was asked for.
    """
    providers = {
        name: provider.model_copy(update={"options": {**provider.options, "lang": language}})
        for name, provider in config.ocr.items()
    }
    return Config(
        general=config.general.model_copy(update={"language": language}),
        preprocess=config.preprocess,
        clean=config.clean,
        ocr=providers,
        correctors=config.correctors,
        source_path=config.source_path,
    )


def build_corrector(config: Config, name: str | None = None) -> TextCorrector | None:
    """Build the text corrector described by the configuration.

    Args:
        config: The effective configuration.
        name: The name of the corrector. Defaults to
            ``[general] text_corrector``.

    Returns:
        The corrector, or ``None`` when there is none: the conversion then
        stays completely offline.

    Raises:
        ConfigurationError: If the corrector is unknown.
    """
    corrector_name = name or config.general.text_corrector
    if not corrector_name:
        return None
    options = config.corrector_provider(corrector_name).options
    if corrector_name == "litellm" or "/" in corrector_name:
        from scan2epub.infrastructure.correction.litellm_corrector import (  # noqa: PLC0415
            LiteLlmCorrector,
        )

        model = str(options.get("model", ""))
        if not model:
            model = corrector_name if "/" in corrector_name else "openai/gpt-4o-mini"
        return LiteLlmCorrector(
            model,
            temperature=float(options.get("temperature", 0.0)),
            max_tokens=int(options.get("max_tokens", 4096)),
            timeout=float(options.get("timeout", 120.0)),
            api_base=options.get("api_base"),
        )
    raise ConfigurationError(
        f"Unknown text corrector {corrector_name!r}. Available correctors: litellm."
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
