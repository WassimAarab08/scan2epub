"""Browser-based end-to-end tests.

These tests open the generated EPUB in a real browser engine (Chromium, via
Playwright) and check the properties that only a real renderer can prove:

* the text is laid out and readable;
* the document **reflows** when the width of the viewport changes;
* the stylesheet does not force the typography of the reader;
* the table of contents links to the chapters;
* the EPUB footnotes are linked to their note;
* the file opens in **foliate-js**, the reference EPUB 3 reader.

The tests are skipped when Playwright or its browser is not installed. Run
``uv run playwright install chromium`` to enable them.
"""

from __future__ import annotations

import functools
import http.server
import shutil
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed.")

pytestmark = pytest.mark.browser

#: The root of the repository.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

#: Where the foliate-js reader is installed.
FOLIATE_DIR = Path(__file__).parent / "assets" / "foliate-js"


@pytest.fixture(scope="session")
def browser() -> Iterator[object]:
    """Return a Chromium browser, or skip the test when it is missing."""
    with playwright_api.sync_playwright() as playwright:
        try:
            instance = playwright.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on the machine
            pytest.skip(f"Chromium is not available: {exc}")
        yield instance
        instance.close()


@pytest.fixture(scope="session")
def page_factory(browser: object) -> Iterator[object]:
    """Return a factory that opens a new page."""
    contexts: list[object] = []

    def factory(**kwargs: object) -> object:
        context = browser.new_context(**kwargs)  # type: ignore[attr-defined]
        contexts.append(context)
        return context.new_page()

    yield factory
    for context in contexts:
        context.close()  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def epub_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return an EPUB generated from the synthetic sample."""
    from scan2epub.application.pipeline import Pipeline
    from scan2epub.config import Config, GeneralConfig
    from scan2epub.domain.models import BookMetadata
    from scan2epub.infrastructure.imaging.opencv_preprocessor import OpenCvPreprocessor
    from scan2epub.infrastructure.ocr.tesseract import TesseractOcrEngine, tesseract_version
    from scan2epub.infrastructure.pdf.pdfium_source import PdfiumPageSource
    from tests.fixtures import make_text_pdf

    if tesseract_version() is None:
        pytest.skip("Tesseract is not installed")

    work = tmp_path_factory.mktemp("browser-work")
    source = make_text_pdf(work / "sample.pdf", pages=3)
    config = Config(general=GeneralConfig(language="eng", validate_epub=False))
    pipeline = Pipeline(
        source=PdfiumPageSource(source, dpi=150),
        preprocessor=OpenCvPreprocessor(config.preprocess),
        ocr=TesseractOcrEngine(lang="eng"),
        config=config,
        work_dir=work / "work",
    )
    output = work / "sample.epub"
    pipeline.run(BookMetadata(title="El libro de prueba", author="Anonimo"), output)
    return output


@pytest.fixture(scope="session")
def unpacked_epub(epub_file: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return the EPUB unpacked in a directory."""
    target = tmp_path_factory.mktemp("epub")
    with zipfile.ZipFile(epub_file) as archive:
        archive.extractall(target)
    return target


@pytest.fixture(scope="session")
def reader_document(unpacked_epub: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return an HTML document that shows the EPUB like a reader would.

    The stylesheet of the book is used verbatim and the typography comes from
    the *browser*, not from the book: that is exactly what an e-reader does.
    """
    stylesheet = (unpacked_epub / "EPUB" / "styles" / "main.css").read_text(encoding="utf-8")
    chapter = next((unpacked_epub / "EPUB" / "text").glob("chapter-*.xhtml"))
    body = chapter.read_text(encoding="utf-8")
    body = body[body.index("<body>") + len("<body>") : body.index("</body>")]

    document = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>scan2epub</title>
<style>
{stylesheet}
html {{ background: #e8e4dd; }}
body {{
  margin: 0 auto; padding: 2rem; max-width: 40rem;
  background: #fbfaf7; color: #1c1a17;
  font-family: "Iowan Old Style", Palatino, Georgia, serif;
  font-size: 19px; line-height: 1.6;
}}
p {{ margin: 0 0 .85em; }}
</style></head>
<body>{body}</body></html>
"""
    target = tmp_path_factory.mktemp("reader") / "reader.html"
    target.write_text(document, encoding="utf-8")
    return target


@pytest.fixture(scope="session")
def site(tmp_path_factory: pytest.TempPathFactory, epub_file: Path) -> Path:
    """Return a directory with the foliate-js reader and the generated book."""
    if not FOLIATE_DIR.is_dir():
        pytest.skip("foliate-js is not installed (run scripts/fetch_browser_assets.py)")
    root = tmp_path_factory.mktemp("site")
    shutil.copytree(FOLIATE_DIR, root / "foliate-js")
    shutil.copy(epub_file, root / "book.epub")
    return root


@pytest.fixture(scope="session")
def http_server(site: Path) -> Iterator[str]:
    """Serve the site directory over HTTP and return its base URL."""

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        """A request handler that does not write to the console."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

        def log_message(self, format: str, *args: object) -> None:
            """Silence the access log."""

    handler = functools.partial(QuietHandler, directory=str(site))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_the_book_is_rendered_by_a_real_browser(
    page_factory: object, reader_document: Path
) -> None:
    """The generated content is laid out and readable in Chromium."""
    page = page_factory()
    page.goto(reader_document.resolve().as_uri())  # type: ignore[attr-defined]
    page.wait_for_selector("p")  # type: ignore[attr-defined]

    text = page.inner_text("body")  # type: ignore[attr-defined]
    assert "El hombre que escribe" in text
    assert "HISTORIA DE LA IMPRENTA" not in text
    assert page.query_selector_all("p")  # type: ignore[attr-defined]


def test_the_document_reflows(page_factory: object, reader_document: Path) -> None:
    """The text flows again when the viewport becomes narrower."""
    page = page_factory(viewport={"width": 1200, "height": 900})
    page.goto(reader_document.resolve().as_uri())  # type: ignore[attr-defined]
    page.wait_for_selector("p")  # type: ignore[attr-defined]

    height_of_first_paragraph = "() => document.querySelector('p').getBoundingClientRect().height"
    wide = page.evaluate(height_of_first_paragraph)  # type: ignore[attr-defined]
    page.set_viewport_size({"width": 420, "height": 900})
    narrow = page.evaluate(height_of_first_paragraph)  # type: ignore[attr-defined]
    assert narrow > wide


def test_the_stylesheet_does_not_force_the_typography(
    page_factory: object, reader_document: Path
) -> None:
    """The computed typography comes from the browser, not from the book."""
    page = page_factory()
    page.goto(reader_document.resolve().as_uri())  # type: ignore[attr-defined]
    page.wait_for_selector("p")  # type: ignore[attr-defined]

    computed = page.evaluate(  # type: ignore[attr-defined]
        "() => { const s = getComputedStyle(document.querySelector('p'));"
        " return {family: s.fontFamily, size: s.fontSize, height: s.lineHeight}; }"
    )
    # The typography comes from the browser: 19 px with a leading of 1.6.
    assert computed["size"] == "19px"
    assert "Iowan Old Style" in computed["family"]
    assert computed["height"] == "30.4px"


def test_the_navigation_links_to_the_chapters(page_factory: object, unpacked_epub: Path) -> None:
    """The navigation document lists the chapters and the links work."""
    page = page_factory()
    nav = (unpacked_epub / "EPUB" / "nav.xhtml").resolve().as_uri()
    page.goto(nav)  # type: ignore[attr-defined]
    page.wait_for_selector("nav")  # type: ignore[attr-defined]

    # The `epub:type` attribute lives in a namespace, so it cannot be
    # selected with a plain CSS attribute selector.
    links = page.evaluate(  # type: ignore[attr-defined]
        "() => Array.from(document.querySelectorAll('nav'))"
        ".filter(nav => nav.getAttribute('epub:type') === 'toc')"
        ".flatMap(nav => Array.from(nav.querySelectorAll('ol a')))"
        ".map(a => a.getAttribute('href'))"
    )
    assert links
    assert links[0].startswith("text/chapter-")

    page.click("nav ol a")  # type: ignore[attr-defined]
    page.wait_for_selector("h1")  # type: ignore[attr-defined]
    assert "CAPITULO PRIMERO" in page.inner_text("h1")  # type: ignore[attr-defined]


def test_the_footnotes_are_linked(page_factory: object, unpacked_epub: Path) -> None:
    """The notes of the book are reachable from the text."""
    page = page_factory()
    chapter = next((unpacked_epub / "EPUB" / "text").glob("chapter-*.xhtml"))
    page.goto(chapter.resolve().as_uri())  # type: ignore[attr-defined]
    page.wait_for_selector("body")  # type: ignore[attr-defined]

    report = page.evaluate(  # type: ignore[attr-defined]
        "() => {"
        " const notes = Array.from(document.querySelectorAll('aside'))"
        "   .filter(a => a.getAttribute('epub:type') === 'footnote');"
        " return notes.map(note => {"
        "   const id = note.getAttribute('id');"
        "   const link = document.querySelector(`a[href='#${id}']`);"
        "   return {id, text: note.textContent.trim().slice(0, 40),"
        "           linked: Boolean(link)}; }); }"
    )
    for note in report:
        assert note["id"]
        assert note["text"]
        assert note["linked"], f"the note {note['id']} is not reachable"


def test_the_epub_opens_in_a_real_reader(page_factory: object, http_server: str) -> None:
    """The generated file opens in foliate-js, a real EPUB 3 reader."""
    page = page_factory()
    page.goto(f"{http_server}/foliate-js/reader.html?url=/book.epub")  # type: ignore[attr-defined]
    page.wait_for_timeout(4000)  # type: ignore[attr-defined]

    texts: list[str] = []
    for frame in page.frames:  # type: ignore[attr-defined]
        try:
            texts.append(frame.inner_text("body"))
        except Exception:  # noqa: S112 - detached frames are not interesting
            continue
    joined = "\n".join(texts)
    assert "El hombre que escribe" in joined
    assert "HISTORIA DE LA IMPRENTA" not in joined


def test_the_reader_builds_the_table_of_contents(page_factory: object, http_server: str) -> None:
    """foliate-js reads the metadata and the navigation of the generated book."""
    page = page_factory()
    page.goto(f"{http_server}/foliate-js/reader.html?url=/book.epub")  # type: ignore[attr-defined]
    page.wait_for_timeout(4000)  # type: ignore[attr-defined]

    # The reader takes the title of the book from the OPF metadata.
    assert "El libro de prueba" in page.title()  # type: ignore[attr-defined]

    # The side bar is collapsed by default: open it to read the table of
    # contents that foliate built from the navigation document.
    page.click("#side-bar-button")  # type: ignore[attr-defined]
    page.wait_for_timeout(800)  # type: ignore[attr-defined]
    toc = page.inner_text("#toc-view")  # type: ignore[attr-defined]
    assert "CAPITULO PRIMERO" in toc


def test_the_chromium_binary_is_present(browser: object) -> None:
    """The Playwright browser is installed and can be launched."""
    assert browser is not None
    version = browser.version  # type: ignore[attr-defined]
    assert version


def test_the_browser_assets_are_installed() -> None:
    """The foliate-js reader is available for the tests."""
    if not FOLIATE_DIR.is_dir():
        pytest.skip("foliate-js is not installed (run scripts/fetch_browser_assets.py)")
    assert (FOLIATE_DIR / "reader.html").is_file()
    assert (FOLIATE_DIR / "epub.js").is_file()
