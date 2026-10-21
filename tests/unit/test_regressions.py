"""Regression tests of the bugs that were found and fixed.

Each test here reproduces a defect that shipped in an earlier version, so that
it can never come back.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scan2epub.application.factory import build_ocr_engine, with_language
from scan2epub.application.pipeline import Pipeline
from scan2epub.application.stages.clean import _continues_previous
from scan2epub.application.stages.headings import classify_heading
from scan2epub.config import Config, GeneralConfig, OcrProviderConfig
from scan2epub.domain.models import BBox, PageImage, TextBlock
from scan2epub.infrastructure.imaging.opencv_preprocessor import OpenCvPreprocessor
from scan2epub.infrastructure.ocr.tesseract import TesseractOcrEngine


def _block(text: str) -> TextBlock:
    """Build a text block with a neutral geometry."""
    return TextBlock(lines=(text,), bbox=BBox(0.1, 0.2, 0.9, 0.24))


def _pipeline(
    language: str,
    work: Path,
    cache: object,
    source: Path,
) -> Pipeline:
    """Build a pipeline for a given language."""
    config = Config(general=GeneralConfig(language=language, validate_epub=False))
    return Pipeline(
        source=PdfiumSourceStub(source),
        preprocessor=OpenCvPreprocessor(config.preprocess),
        ocr=TesseractOcrEngine(lang=language),
        config=config,
        work_dir=work,
        cache=cache,  # type: ignore[arg-type]
    )


class PdfiumSourceStub:
    """A page source that does not need a real PDF."""

    def __init__(self, path: Path) -> None:
        """Remember where the fake page would be."""
        self.path = path

    def pages(self) -> list[PageImage]:
        """Return a single fake page."""
        return [PageImage(index=0, path=self.path, width=100, height=100)]


def test_the_cache_key_depends_on_the_language(tmp_path: Path) -> None:
    """Two languages must never share their cached recognition.

    Before the fix, the key only covered the pre-processing options, so a
    book recognised in English was served again when the language changed to
    Spanish.
    """
    from scan2epub.application.cache import FileCache

    page = tmp_path / "page.png"
    page.write_bytes(b"not a real image")
    cache = FileCache(tmp_path / "cache")

    keys = {}
    for language in ("eng", "spa"):
        pipeline = _pipeline(language, tmp_path / language, cache, page)
        image = PageImage(index=0, path=page, width=100, height=100)
        keys[language] = pipeline._ocr_cache_key(image)

    assert keys["eng"] != keys["spa"]


def test_the_cache_key_depends_on_the_engine_settings(tmp_path: Path) -> None:
    """Two different segmentations must not share their artefacts."""
    from scan2epub.application.cache import FileCache

    page = tmp_path / "page.png"
    page.write_bytes(b"not a real image")
    cache = FileCache(tmp_path / "cache")
    config = Config(general=GeneralConfig(language="eng", validate_epub=False))

    keys = []
    for psm in (3, 6):
        pipeline = Pipeline(
            source=PdfiumSourceStub(page),
            preprocessor=OpenCvPreprocessor(config.preprocess),
            ocr=TesseractOcrEngine(lang="eng", psm=psm),
            config=config,
            work_dir=tmp_path / str(psm),
            cache=cache,
        )
        image = PageImage(index=0, path=page, width=100, height=100)
        keys.append(pipeline._ocr_cache_key(image))

    assert keys[0] != keys[1]


def test_the_command_line_language_wins_over_the_file() -> None:
    """``--lang`` must win over the ``[ocr.tesseract] lang`` of the file.

    Before the fix, the provider section always won and the language of the
    command line was silently ignored.
    """
    config = Config(
        general=GeneralConfig(language="spa"),
        ocr={"tesseract": OcrProviderConfig(options={"lang": "fra"})},
    )
    assert build_ocr_engine(config).lang == "fra"  # type: ignore[attr-defined]

    overridden = with_language(config, "eng")
    assert build_ocr_engine(overridden).lang == "eng"  # type: ignore[attr-defined]
    assert build_ocr_engine(overridden, language="deu").lang == "deu"  # type: ignore[attr-defined]


def test_the_language_override_also_changes_the_provider() -> None:
    """The provider section follows the language, so the cache agrees."""
    config = Config(
        general=GeneralConfig(language="spa"),
        ocr={"tesseract": OcrProviderConfig(options={"lang": "fra"})},
    )
    overridden = with_language(config, "eng")
    assert overridden.ocr_provider("tesseract").options["lang"] == "eng"


def test_the_options_of_a_provider_are_read(tmp_path: Path) -> None:
    """The settings written in the file must reach the engine.

    Before the fix, the keys of a provider section were stored apart from
    its ``options`` table, so the documented ``[ocr.tesseract] lang = "fra"``
    was silently ignored and the engine used the general language.
    """
    from scan2epub.config import load_config

    direct = tmp_path / "direct.toml"
    direct.write_text(
        '[general]\nlanguage = "spa"\n\n[ocr.tesseract]\nlang = "fra"\n',
        encoding="utf-8",
    )
    config = load_config(direct)
    assert config.ocr_provider("tesseract").options["lang"] == "fra"
    assert build_ocr_engine(config).lang == "fra"  # type: ignore[attr-defined]

    nested = tmp_path / "nested.toml"
    nested.write_text(
        '[general]\nlanguage = "spa"\n\n'
        '[ocr.tesseract]\nlang = "fra"\n\n'
        '[ocr.tesseract.options]\nlang = "deu"\npsm = 6\n',
        encoding="utf-8",
    )
    config = load_config(nested)
    # The sub-table wins over the direct key.
    assert config.ocr_provider("tesseract").options["lang"] == "deu"
    assert config.ocr_provider("tesseract").options["psm"] == 6
    engine = build_ocr_engine(config)
    assert engine.lang == "deu"  # type: ignore[attr-defined]
    assert engine.psm == 6  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "text",
    [
        "Book the tickets before the concert.",
        "Part of the problem is that nobody reads the notes.",
        "Books are still the best way to learn a language.",
        "Partly cloudy, with a chance of rain.",
    ],
)
def test_an_ordinary_sentence_is_not_a_heading(text: str) -> None:
    """A sentence that starts with a structural word is not a heading.

    Before the fix, "Book" and "Part" turned whole paragraphs into chapters.
    """
    assert classify_heading(_block(text)) is None


@pytest.mark.parametrize(
    ("text", "level"),
    [
        ("CAPITULO PRIMERO", 1),
        ("Chapter Four", 1),
        ("Book One", 1),
        ("Chapter 12", 1),
        ("CAPITULO", 1),
        ("PARTE SEGUNDA", 1),
    ],
)
def test_a_real_heading_is_still_a_heading(text: str, level: int) -> None:
    """The tightening of the rule did not break the real headings."""
    assert classify_heading(_block(text)) == level


def test_a_word_that_ends_with_a_conjunction_is_not_a_conjunction() -> None:
    """``The company`` does not end with the conjunction ``y``.

    Before the fix, any word ending with ``y``, ``e``, ``o``, ``u`` or ``i``
    was treated as a conjunction, so unrelated paragraphs were merged.
    """
    assert not _continues_previous("The company", "President announced it.")
    assert _continues_previous("bread and", "butter")


def test_a_note_that_the_ocr_split_keeps_its_text() -> None:
    """A note cut in two by the OCR must not lose its second half.

    Before the fix, the second half of a note carried no marker of its own,
    so it was dropped when the notes were collected.
    """
    from scan2epub.application.stages.clean import clean_pages
    from scan2epub.domain.models import BlockKind, PageContent

    def note(lines: tuple[str, ...], order: int) -> TextBlock:
        return TextBlock(
            lines=lines,
            bbox=BBox(0.1, 0.85, 0.9, 0.9),
            kind=BlockKind.BODY,
            order=order,
            page=0,
        )

    pages = [
        PageContent(
            index=0,
            blocks=(
                note(("1 Nota del autor sobre la",), 0),
                note(("imprenta y sus costes.",), 1),
            ),
        )
    ]
    result = clean_pages(pages)
    notes = [block for block in result.pages[0].blocks if block.kind is BlockKind.FOOTNOTE]
    assert len(notes) == 1
    assert "imprenta y sus costes." in notes[0].text


def test_two_notes_with_their_own_number_are_not_merged() -> None:
    """A note that carries a number of its own is a different note."""
    from scan2epub.application.stages.clean import clean_pages
    from scan2epub.domain.models import BlockKind, PageContent

    def note(text: str, order: int) -> TextBlock:
        return TextBlock(
            lines=(text,),
            bbox=BBox(0.1, 0.85, 0.9, 0.9),
            kind=BlockKind.BODY,
            order=order,
            page=0,
        )

    pages = [
        PageContent(
            index=0,
            blocks=(
                note("1 Primera nota", 0),
                note("2 Segunda nota", 1),
            ),
        )
    ]
    result = clean_pages(pages)
    notes = [block for block in result.pages[0].blocks if block.kind is BlockKind.FOOTNOTE]
    assert len(notes) == 2


def test_a_comma_still_continues_the_paragraph() -> None:
    """A line that ends with a comma continues the paragraph."""
    assert _continues_previous("la casa, el jardín", "y el patio")
    assert _continues_previous("la casa,", "el jardín")


def test_the_notes_of_a_chapter_have_unique_identifiers(tmp_path: Path) -> None:
    """Two notes with the same number must not share an identifier.

    Before the fix, the identifier was built from the number of the note, so
    a book that numbers its notes again on every page produced duplicate
    identifiers, which is invalid XML.
    """
    import re
    import zipfile

    from scan2epub.domain.models import BlockKind, Book, BookMetadata, Chapter
    from scan2epub.infrastructure.epub.writer import EpubWriter

    def note(page: int, order: int) -> TextBlock:
        return TextBlock(
            lines=("1 Nota del autor.",),
            bbox=BBox(0.1, 0.85, 0.9, 0.9),
            kind=BlockKind.FOOTNOTE,
            order=order,
            page=page,
        )

    def body(text: str, page: int, order: int) -> TextBlock:
        return TextBlock(
            lines=(text,),
            bbox=BBox(0.1, 0.2, 0.9, 0.3),
            kind=BlockKind.BODY,
            order=order,
            page=page,
        )

    chapter = Chapter(
        id="chapter-1",
        title="Capitulo",
        blocks=(
            body("El texto 1 y su continuacion.", 0, 0),
            note(0, 1),
            body("Mas texto 1 aqui.", 1, 2),
            note(1, 3),
        ),
    )
    book = Book(
        metadata=BookMetadata(title="Libro"),
        chapters=(chapter,),
    )
    target = tmp_path / "book.epub"
    EpubWriter().write(book, target)

    with zipfile.ZipFile(target) as archive:
        document = archive.read("EPUB/text/chapter-001.xhtml").decode("utf-8")

    identifiers = re.findall(r'<aside epub:type="footnote" id="([^"]+)"', document)
    assert len(identifiers) == 2
    assert len(set(identifiers)) == 2, f"duplicate identifiers: {identifiers}"
