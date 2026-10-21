"""Tests of the command line interface."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scan2epub.cli.main import app
from scan2epub.infrastructure.ocr.tesseract import tesseract_version

runner = CliRunner()


def test_the_help_is_shown() -> None:
    """``--help`` lists the commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "convert" in result.output
    assert "doctor" in result.output


def test_the_version_is_shown() -> None:
    """``--version`` prints the version."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "scan2epub" in result.output


def test_doctor_reports_the_environment() -> None:
    """``doctor`` describes the installation."""
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "scan2epub" in result.output
    assert "tesseract" in result.output


def test_doctor_can_print_json() -> None:
    """``doctor --json`` produces machine readable output."""
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "tesseract" in payload
    assert "api_keys_present" in payload


def test_doctor_never_prints_the_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """The credentials are reported as present or absent, never as a value."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-supersecretvalue1234567890")
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    assert "sk-supersecretvalue1234567890" not in result.output
    assert json.loads(result.output)["api_keys_present"]["OPENAI_API_KEY"] is True


def test_a_missing_input_is_reported(sample_pdf: Path) -> None:
    """A file that does not exist is a usage error."""
    result = runner.invoke(app, ["convert", "does-not-exist.pdf"])
    assert result.exit_code != 0


def test_the_conversion_runs(sample_pdf: Path, tmp_path: Path) -> None:
    """The ``convert`` command produces an EPUB."""
    if tesseract_version() is None:
        pytest.skip("Tesseract is not installed")
    output = tmp_path / "book.epub"
    result = runner.invoke(
        app,
        [
            "convert",
            str(sample_pdf),
            "-o",
            str(output),
            "--lang",
            "eng",
            "--work-dir",
            str(tmp_path / "work"),
            "--no-validate",
        ],
    )
    assert result.exit_code == 0, result.output
    assert output.is_file()
    with zipfile.ZipFile(output) as archive:
        assert "EPUB/package.opf" in archive.namelist()


def test_the_conversion_can_print_json(sample_pdf: Path, tmp_path: Path) -> None:
    """``--json`` prints a machine readable summary."""
    if tesseract_version() is None:
        pytest.skip("Tesseract is not installed")
    result = runner.invoke(
        app,
        [
            "convert",
            str(sample_pdf),
            "-o",
            str(tmp_path / "book.epub"),
            "--lang",
            "eng",
            "--work-dir",
            str(tmp_path / "work"),
            "--no-validate",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["pages"] == 3
    assert payload["removed_running_heads"]
