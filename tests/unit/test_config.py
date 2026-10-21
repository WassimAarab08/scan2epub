"""Tests for the configuration handling."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from scan2epub.config import (
    CleanConfig,
    Config,
    GeneralConfig,
    PreprocessConfig,
    default_config_path,
    load_config,
    output_language_for,
)
from scan2epub.errors import ConfigurationError


def test_the_defaults_are_usable() -> None:
    """A configuration without a file is perfectly valid."""
    config = load_config(Path("does-not-exist.toml")) if False else Config()
    assert config.general.dpi == 300
    assert config.general.ocr_engine == "tesseract"
    assert config.general.validate_epub is True
    assert config.preprocess.deskew is True
    assert config.clean.min_running_head_repeats == 3


def test_a_toml_file_is_loaded(tmp_path: Path) -> None:
    """Every section of the file is read."""
    path = tmp_path / "config.toml"
    path.write_text(
        """
[general]
dpi = 400
language = "spa_old"
title = "El libro"

[preprocess]
binarize = false
crop_margin = 24

[clean]
min_running_head_repeats = 5

[ocr.tesseract]
lang = "spa+eng"
oem = 1

[ocr.tesseract.options]
tessdata_dir = "/opt/tessdata"
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.general.dpi == 400
    assert config.general.language == "spa_old"
    assert config.general.title == "El libro"
    assert config.preprocess.binarize is False
    assert config.preprocess.crop_margin == 24
    assert config.clean.min_running_head_repeats == 5
    assert config.ocr_provider("tesseract").options["tessdata_dir"] == "/opt/tessdata"
    assert config.source_path == path


def test_an_unknown_key_is_rejected(tmp_path: Path) -> None:
    """A typo in the configuration file is an error, not a silent default."""
    path = tmp_path / "config.toml"
    path.write_text("[general]\ndpii = 300\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_an_invalid_value_is_rejected(tmp_path: Path) -> None:
    """Out-of-range values are refused."""
    path = tmp_path / "config.toml"
    path.write_text("[general]\ndpi = 99999\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_a_broken_file_is_reported(tmp_path: Path) -> None:
    """A syntax error is reported with a clear message."""
    path = tmp_path / "config.toml"
    path.write_text("[general\ndpi = 300\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_a_missing_file_is_reported(tmp_path: Path) -> None:
    """An explicitly requested file that does not exist is an error."""
    with pytest.raises(ConfigurationError):
        load_config(tmp_path / "nope.toml")


def test_the_environment_overrides_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment variables win over the configuration file."""
    path = tmp_path / "config.toml"
    path.write_text("[general]\ndpi = 300\n", encoding="utf-8")
    monkeypatch.setenv("SCAN2EPUB_GENERAL_DPI", "600")
    config = load_config(path)
    assert config.general.dpi == 600


def test_the_default_configuration_path_is_under_the_home() -> None:
    """The default configuration lives in the user configuration directory."""
    assert default_config_path().name == "config.toml"
    assert default_config_path().parent.name == "scan2epub"


@pytest.mark.parametrize(
    ("ocr_language", "expected"),
    [
        ("spa", "es"),
        ("spa_old", "es"),
        ("eng", "en"),
        ("fra+eng", "fr"),
        ("unknown", "es"),
    ],
)
def test_the_ocr_language_is_mapped_to_a_bcp47_tag(ocr_language: str, expected: str) -> None:
    """Tesseract uses three-letter codes, EPUB needs the two-letter form."""
    assert output_language_for(ocr_language) == expected


def test_the_sections_are_frozen() -> None:
    """A configuration section cannot be modified in place."""
    with pytest.raises(ValidationError):
        GeneralConfig().dpi = 100  # type: ignore[misc]


def test_an_unknown_provider_returns_the_defaults() -> None:
    """Asking for an undeclared provider is not an error."""
    config = Config()
    assert config.ocr_provider("nope").options == {}
    assert config.corrector_provider("nope").adapter is None


def test_the_clean_and_preprocess_sections_have_defaults() -> None:
    """The sections can be built without arguments."""
    assert CleanConfig().header_zone == 0.12
    assert PreprocessConfig().binary_block_size == 31
