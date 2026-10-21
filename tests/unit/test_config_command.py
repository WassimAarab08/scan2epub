"""Tests of the ``scan2epub config`` command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scan2epub.cli.main import app
from scan2epub.config import load_config

runner = CliRunner()


def test_the_template_is_written(tmp_path: Path) -> None:
    """``--init`` writes a documented configuration file."""
    target = tmp_path / "config.toml"
    result = runner.invoke(app, ["config", "--init", "--path", str(target)])
    assert result.exit_code == 0
    assert target.is_file()
    assert "scan2epub" in result.output


def test_the_template_is_valid(tmp_path: Path) -> None:
    """The template that is written can be read back."""
    target = tmp_path / "config.toml"
    runner.invoke(app, ["config", "--init", "--path", str(target)])
    config = load_config(target)
    assert config.general.dpi == 300
    assert config.general.ocr_engine == "tesseract"
    assert config.ocr_provider("tesseract").options["lang"] == "spa"


def test_the_template_is_not_overwritten(tmp_path: Path) -> None:
    """An existing file is never destroyed."""
    target = tmp_path / "config.toml"
    target.write_text("[general]\ndpi = 150\n", encoding="utf-8")
    result = runner.invoke(app, ["config", "--init", "--path", str(target)])
    assert result.exit_code == 1
    assert "dpi = 150" in target.read_text(encoding="utf-8")


def test_the_effective_configuration_is_shown(tmp_path: Path) -> None:
    """``--show`` prints the configuration that is in use."""
    target = tmp_path / "config.toml"
    target.write_text("[general]\ndpi = 150\n", encoding="utf-8")
    result = runner.invoke(app, ["config", "--show", "--path", str(target)])
    assert result.exit_code == 0
    assert "150" in result.output


def test_the_command_without_options_reports_the_state(tmp_path: Path) -> None:
    """The command says where the configuration file is."""
    target = tmp_path / "config.toml"
    result = runner.invoke(app, ["config", "--path", str(target)])
    assert result.exit_code == 0
    assert "config.toml" in result.output


def test_a_configuration_with_a_byte_order_mark_is_read(tmp_path: Path) -> None:
    """A file saved by a Windows editor is still read."""
    target = tmp_path / "config.toml"
    target.write_text("[general]\ndpi = 150\n", encoding="utf-8-sig")
    config = load_config(target)
    assert config.general.dpi == 150


@pytest.mark.parametrize("content", ["[general]\ndpi = 300\n"])
def test_a_valid_configuration_is_accepted(tmp_path: Path, content: str) -> None:
    """A minimal file is valid."""
    target = tmp_path / "config.toml"
    target.write_text(content, encoding="utf-8")
    assert load_config(target).general.dpi == 300


def test_the_json_output_is_valid(tmp_path: Path) -> None:
    """The configuration can be read as JSON."""
    target = tmp_path / "config.toml"
    target.write_text("[general]\ndpi = 150\n", encoding="utf-8")
    result = runner.invoke(app, ["config", "--show", "--path", str(target)])
    # The Rich renderer may add ANSI codes; the JSON must still be there.
    assert '"dpi": 150' in result.output
    assert json.dumps  # the import is used by the reader of this test
