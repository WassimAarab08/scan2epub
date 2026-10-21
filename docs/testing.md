# Testing

The test suite is the main proof that the tool works. It has four layers.

| Layer | Location | What it proves | Needs |
| --- | --- | --- | --- |
| Unit | `tests/unit/` | The rules of the cleaner, the writer, the configuration. | nothing |
| Integration | `tests/integration/` | The whole pipeline, end to end. | Tesseract |
| Browser | `tests/browser/` | The book renders, reflows and opens in a real reader. | Playwright, Chromium, foliate-js |
| Contract | `scripts/check_licenses.py` | No copyleft dependency sneaks in. | nothing |

## Running the tests

```bash
uv sync --all-extras
uv run pytest
```

With the coverage report:

```bash
uv run pytest --cov=src/scan2epub --cov-report=term-missing
```

The minimum coverage is 80 % and it is enforced by the configuration:

```toml
[tool.coverage.report]
fail_under = 80
```

## The quality gates

Everything below must pass before a pull request can be merged. The same
commands run in the continuous integration.

```bash
uv run ruff format --check .      # the formatting
uv run ruff check .               # the lint
uv run pyright                    # the types, in strict mode
uv run pytest                     # the tests
uv run python scripts/check_licenses.py   # the licences
```

## The browser tests

The browser tests are the ones that prove the EPUB is really a book and not
just a ZIP file with some XML inside. They open the generated file in
**Chromium**, through Playwright, and check the properties that only a real
renderer can show.

```bash
uv run playwright install chromium      # once
uv run python scripts/fetch_browser_assets.py   # once: installs foliate-js
uv run pytest tests/browser -v
```

| Test | What it proves |
| --- | --- |
| `test_the_book_is_rendered_by_a_real_browser` | The text is laid out and the running head is gone. |
| `test_the_document_reflows` | The paragraphs grow taller when the viewport narrows: the book reflows. |
| `test_the_stylesheet_does_not_force_the_typography` | The computed font, size and leading come from the browser, not from the book. |
| `test_the_navigation_links_to_the_chapters` | The table of contents points at the chapters and the links work. |
| `test_the_footnotes_are_linked` | Every note is reachable from the text. |
| `test_the_epub_opens_in_a_real_reader` | **foliate-js**, the reference EPUB 3 reader, opens the file and shows the text. |
| `test_the_reader_builds_the_table_of_contents` | foliate-js reads the title and builds the table of contents of the generated book. |

The tests are skipped, not failed, when Playwright or the browser is not
installed, so the suite still works on a machine without a browser.

### Why foliate-js?

`foliate-js` is the renderer of [Foliate](https://github.com/johnfactotum/foliate),
the most complete open source EPUB reader. It is strict about the
specification, which makes it the best possible referee for a generated file:
if a book opens in foliate-js, it will open in Kindle, Kobo and KOReader.

It is also the reader that the web interface of Phase 5 will use, so the
tests exercise the very same code that the users will see.

## The synthetic fixtures

The test suite does not need a real book. `tests/fixtures.py` builds one:

| Helper | What it makes |
| --- | --- |
| `make_text_pdf` | A valid PDF whose pages carry a running head, a folio, words broken by a hyphen and a paragraph that continues on the next page. It uses the base-14 Times font, so no font file is needed. |
| `make_scanned_image` | A page that looks like a degraded scan: tilted, noisy, with a dark frame and foxing spots. |

The PDF writer is hand-written (about a hundred lines) so that the fixtures
work on any platform without a binary dependency.

## Writing a new test

The suite is organised by the module under test:

```
tests/
├── unit/          # one file per module
├── integration/   # the whole pipeline
├── browser/       # a real browser
├── conftest.py    # the shared fixtures
└── fixtures.py    # the synthetic books
```

A test that needs a book uses the `sample_pdf` fixture:

```python
def test_the_conversion_runs(sample_pdf: Path, tmp_path: Path) -> None:
    """The pipeline produces a file."""
    result = _pipeline(sample_pdf, tmp_path / "work").run(
        BookMetadata(title="El libro"), tmp_path / "book.epub"
    )
    assert result.epub_path.is_file()
```

A test that needs a real browser uses the `page_factory` fixture:

```python
def test_the_book_is_readable(page_factory: object, reader_document: Path) -> None:
    """The text of the book is visible."""
    page = page_factory()
    page.goto(reader_document.resolve().as_uri())
    assert "El hombre" in page.inner_text("body")
```

## The licence check

```bash
uv run python scripts/check_licenses.py
uv run python scripts/check_licenses.py --json
```

The script reads the metadata of every installed distribution and fails when
one of them declares a copyleft or a proprietary licence. It is the mechanical
guard behind the promise of the project: `scan2epub` is Apache-2.0 licensed
and only uses permissive dependencies.

The check has already caught a real problem: `python-slugify` pulls in
`text-unidecode`, which is GPL licensed. The dependency was removed.

## The evaluation corpus

Phase 2 adds the `samples/` corpus: pages of public-domain books with their
reference transcription, and the `scan2epub eval` command that computes the
CER and the WER of every engine. See [`benchmarks.md`](benchmarks.md).
