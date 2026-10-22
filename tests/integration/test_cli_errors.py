"""Tests for the error messages of the CLI and for the language table."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scan2epub.cli.main import app
from scan2epub.config import output_language_for
from scan2epub.domain.languages import LANGUAGE_CODES, ocr_languages
from tests.support import strip_ansi

runner = CliRunner()


def test_a_file_that_does_not_exist_is_reported(tmp_path: Path) -> None:
    """A missing file is a usage error."""
    result = runner.invoke(app, ["convert", str(tmp_path / "nope.pdf")])
    assert result.exit_code != 0


def test_a_directory_is_reported(tmp_path: Path) -> None:
    """A directory is not a book."""
    result = runner.invoke(app, ["convert", str(tmp_path)])
    assert result.exit_code != 0
    assert "does not exist" in result.output or "file" in result.output.lower()


def test_a_file_that_is_not_a_pdf_is_reported(tmp_path: Path) -> None:
    """A file that is not a PDF says so, and says what to do."""
    broken = tmp_path / "not-a-book.pdf"
    broken.write_bytes(b"this is definitely not a PDF")
    result = runner.invoke(app, ["convert", str(broken)])
    assert result.exit_code == 1
    assert "could not be opened as a PDF" in strip_ansi(result.output)
    assert "scan" in strip_ansi(result.output).lower()


def test_an_empty_file_is_reported(tmp_path: Path) -> None:
    """An empty file says that a book needs at least one page."""
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    result = runner.invoke(app, ["convert", str(empty)])
    assert result.exit_code == 1
    assert "at least one page" in strip_ansi(result.output)


def test_a_pdf_that_cannot_be_read_is_reported(tmp_path: Path) -> None:
    """A PDF whose page tree is broken is refused."""
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\nnot really a PDF at all\n%%EOF\n")
    result = runner.invoke(app, ["convert", str(broken)])
    assert result.exit_code == 1
    assert "Error" in strip_ansi(result.output)


def test_the_error_message_says_what_to_do(tmp_path: Path) -> None:
    """Every message of the library ends with a hint."""
    broken = tmp_path / "not-a-book.pdf"
    broken.write_bytes(b"nope")
    result = runner.invoke(app, ["convert", str(broken)])
    message = strip_ansi(result.output)
    assert "Error:" in message
    # The message mentions the file and what to do.
    assert "not-a-book.pdf" in message
    assert message.rstrip().endswith(".")


@pytest.mark.parametrize(
    ("code", "tag"),
    [
        ("spa", "es"),
        ("spa_old", "es"),
        ("eng", "en"),
        ("fra", "fr"),
        ("cat", "ca"),
        ("glg", "gl"),
        ("eus", "eu"),
        ("chi_sim", "zh"),
        ("jpn", "ja"),
        ("kor", "ko"),
        ("rus", "ru"),
        ("ell", "el"),
        ("heb", "he"),
        ("ara", "ar"),
        ("hin", "hi"),
        ("vie", "vi"),
    ],
)
def test_the_language_codes_are_mapped(code: str, tag: str) -> None:
    """The codes of Tesseract are mapped to the tags of BCP-47."""
    assert LANGUAGE_CODES[code] == tag
    assert output_language_for(code) == tag


def test_a_combination_of_languages_uses_the_first_one() -> None:
    """``spa+eng`` is a Spanish book."""
    assert output_language_for("spa+eng") == "es"
    assert output_language_for("eng+spa") == "en"


def test_an_unknown_language_falls_back() -> None:
    """An unknown code does not break the conversion."""
    assert output_language_for("xyz") == "es"
    assert output_language_for("xyz", "en") == "en"


def test_every_code_is_a_valid_bcp47_tag() -> None:
    """No tag of the table is malformed."""
    for code, tag in LANGUAGE_CODES.items():
        assert tag, code
        assert "-" not in tag or tag.count("-") == 1, tag
        assert tag.replace("-", "").isalnum(), tag


def test_the_orientation_data_is_not_a_language() -> None:
    """``osd`` is the orientation data, not a language."""
    assert "osd" not in ocr_languages()
    assert "eng" in ocr_languages()


def test_the_language_table_is_in_the_documentation() -> None:
    """The table of the documentation mentions the languages."""
    root = Path(__file__).resolve().parent.parent.parent
    document = (root / "docs" / "configuration.md").read_text(encoding="utf-8")
    for code in ("spa", "spa_old", "eng", "fra", "deu", "ita", "por", "lat"):
        assert f"`{code}`" in document, code
    # The JSON of the doctor mentions the languages of Tesseract.
    result = runner.invoke(app, ["doctor", "--json"])
    assert json.loads(strip_ansi(result.output))["tesseract"]["languages"]
