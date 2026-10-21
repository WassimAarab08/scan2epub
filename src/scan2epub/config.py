"""Configuration handling.

The configuration is layered, from the lowest to the highest priority:

1. the defaults defined in this module;
2. the ``config.toml`` file (see ``docs/configuration.md``);
3. environment variables prefixed with ``SCAN2EPUB_``;
4. explicit command line options.

Only the values that are safe to expose are read from the environment. API
keys are never stored in ``config.toml``: they are read directly from the
environment by the adapters that need them and are never logged.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from scan2epub.domain.languages import LANGUAGE_CODES, ocr_languages
from scan2epub.errors import ConfigurationError

__all__ = [
    "LANGUAGE_CODES",
    "CleanConfig",
    "Config",
    "GeneralConfig",
    "OcrProviderConfig",
    "PreprocessConfig",
    "default_config_path",
    "load_config",
    "ocr_languages",
    "output_language_for",
]

ENV_PREFIX: Final[str] = "SCAN2EPUB_"


def output_language_for(ocr_language: str, default: str = "es") -> str:
    """Return the BCP-47 language tag that matches an OCR language.

    Tesseract uses three-letter codes (``spa``, ``eng``) while EPUB requires
    the two-letter BCP-47 form (``es``, ``en``).

    Args:
        ocr_language: The OCR language, possibly a ``+`` separated list.
        default: The tag returned when no mapping is known.

    Returns:
        The BCP-47 language tag.
    """
    for part in ocr_language.split("+"):
        tag = part.strip().lower()
        if tag in LANGUAGE_CODES:
            return LANGUAGE_CODES[tag]
    return default


class _Section(BaseModel):
    """Base class for the configuration sections."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class GeneralConfig(_Section):
    """Global options."""

    dpi: int = Field(default=300, ge=72, le=1200)
    language: str = "spa"
    ocr_engine: str = "tesseract"
    text_corrector: str | None = None
    modernize: bool = False
    output_language: str | None = None
    title: str | None = None
    author: str | None = None
    year: str | None = None
    validate_epub: bool = True


class PreprocessConfig(_Section):
    """Image clean-up options applied before OCR."""

    deskew: bool = True
    max_skew_degrees: float = Field(default=5.0, ge=0.0, le=45.0)
    binarize: bool = True
    denoise: bool = True
    crop_borders: bool = True
    crop_margin: int = Field(default=16, ge=0, le=256)
    binary_block_size: int = Field(default=31, ge=3, le=255)
    binary_c: int = Field(default=12, ge=0, le=255)


class CleanConfig(_Section):
    """Deterministic text-cleaning options."""

    header_zone: float = Field(default=0.12, ge=0.0, lt=0.5)
    footer_zone: float = Field(default=0.12, ge=0.0, lt=0.5)
    footnote_zone: float = Field(default=0.82, ge=0.0, le=1.0)
    min_running_head_repeats: int = Field(default=3, ge=2, le=100)
    max_running_head_chars: int = Field(default=90, ge=10, le=500)
    join_hyphens: bool = True
    normalize_characters: bool = True
    join_paragraphs: bool = True
    detect_footnotes: bool = True
    keep_footnotes_inline: bool = False


class OcrProviderConfig(_Section):
    """Options of a single OCR provider declared in ``config.toml``."""

    adapter: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow", frozen=True)


def _empty_providers() -> dict[str, OcrProviderConfig]:
    """Return an empty provider table."""
    return {}


@dataclass(frozen=True, slots=True)
class Config:
    """The effective configuration of a run."""

    general: GeneralConfig = field(default_factory=GeneralConfig)
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    clean: CleanConfig = field(default_factory=CleanConfig)
    ocr: dict[str, OcrProviderConfig] = field(default_factory=_empty_providers)
    correctors: dict[str, OcrProviderConfig] = field(default_factory=_empty_providers)
    source_path: Path | None = None

    def ocr_provider(self, name: str) -> OcrProviderConfig:
        """Return the configuration of the OCR provider ``name``."""
        return self.ocr.get(name, OcrProviderConfig())

    def corrector_provider(self, name: str) -> OcrProviderConfig:
        """Return the configuration of the text corrector ``name``."""
        return self.correctors.get(name, OcrProviderConfig())


def default_config_path() -> Path:
    """Return the path of the user-wide configuration file."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "scan2epub" / "config.toml"


def _find_config_file(explicit: Path | None) -> Path | None:
    if explicit is not None:
        if not explicit.is_file():
            raise ConfigurationError(f"Configuration file not found: {explicit}")
        return explicit
    env_path = os.environ.get(f"{ENV_PREFIX}CONFIG")
    if env_path:
        candidate = Path(env_path)
        if not candidate.is_file():
            raise ConfigurationError(f"Configuration file not found: {candidate}")
        return candidate
    candidate = default_config_path()
    return candidate if candidate.is_file() else None


def _apply_environment(section: type[_Section], values: dict[str, Any]) -> dict[str, Any]:
    """Override section values from ``SCAN2EPUB_<SECTION>_<FIELD>`` variables."""
    for key in list(values):
        env_name = f"{ENV_PREFIX}{section.__name__.removesuffix('Config').upper()}_{key.upper()}"
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        current = values[key]
        if isinstance(current, bool):
            values[key] = raw.strip().lower() in {"1", "true", "yes", "on"}
        elif isinstance(current, int) and not isinstance(current, bool):
            values[key] = int(raw)
        elif isinstance(current, float):
            values[key] = float(raw)
        elif current is None:
            values[key] = raw
        else:
            values[key] = raw
    return values


def _build_section(section: type[_Section], raw: dict[str, Any]) -> Any:  # noqa: ANN401
    """Build a configuration section, applying the environment overrides."""
    values = _apply_environment(section, dict(raw))
    try:
        return section(**values)
    except ValidationError as exc:  # pragma: no cover - defensive
        raise ConfigurationError(f"Invalid configuration: {exc}") from exc


def _split_providers(raw: dict[str, Any], prefix: str) -> dict[str, OcrProviderConfig]:
    """Build the provider sections of the configuration file.

    Every key of the section except ``adapter`` becomes an option, whether it
    is written directly (``[ocr.tesseract] lang = "spa"``) or in a sub-table
    (``[ocr.tesseract.options] lang = "spa"``). The sub-table wins when both
    are present.
    """
    providers: dict[str, OcrProviderConfig] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            continue
        table = cast("dict[str, Any]", body)
        raw_options = table.get("options")
        sub_table: dict[str, Any] = (
            cast("dict[str, Any]", raw_options) if isinstance(raw_options, dict) else {}
        )
        direct = {key: value for key, value in table.items() if key not in {"adapter", "options"}}
        options: dict[str, Any] = {**direct, **sub_table}
        raw_adapter = table.get("adapter")
        adapter = raw_adapter if isinstance(raw_adapter, str) else None
        try:
            providers[name] = OcrProviderConfig(adapter=adapter, options=options)
        except ValidationError as exc:
            raise ConfigurationError(f"Invalid [{prefix}.{name}] section: {exc}") from exc
    return providers


def _table(raw: dict[str, Any], name: str) -> dict[str, Any]:
    """Return a sub-table of the configuration file."""
    value = raw.get(name)
    if not isinstance(value, dict):
        return {}
    return cast("dict[str, Any]", value)


def load_config(path: Path | None = None) -> Config:
    """Load the effective configuration.

    Args:
        path: An explicit ``config.toml`` path. When omitted, the
            ``SCAN2EPUB_CONFIG`` environment variable and the default user
            configuration file are consulted.

    Returns:
        The merged configuration.

    Raises:
        ConfigurationError: If the file cannot be parsed or contains invalid
            values.
    """
    config_file = _find_config_file(path)
    raw: dict[str, Any] = {}
    if config_file is not None:
        try:
            # "utf-8-sig" tolerates a byte order mark.
            parsed = tomllib.loads(config_file.read_text(encoding="utf-8-sig"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(f"Cannot parse {config_file}: {exc}") from exc
        raw = dict(parsed)

    general = _build_section(GeneralConfig, _table(raw, "general"))
    preprocess = _build_section(PreprocessConfig, _table(raw, "preprocess"))
    clean = _build_section(CleanConfig, _table(raw, "clean"))
    ocr = _split_providers(_table(raw, "ocr"), "ocr")
    correctors = _split_providers(_table(raw, "correct"), "correct")

    return Config(
        general=general,
        preprocess=preprocess,
        clean=clean,
        ocr=ocr,
        correctors=correctors,
        source_path=config_file,
    )
