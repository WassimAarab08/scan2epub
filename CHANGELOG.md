# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **The conversion is a job, not a request.** `POST /api/jobs` queues a
  conversion in SQLite, a worker runs it in the background, and
  `GET /api/jobs/{id}/events` streams the progress as Server-Sent Events,
  replaying the events that a client that arrives late has missed. The jobs
  can be listed, cancelled and resumed.
- **An Angular interface with the reader inside.** Upload by drag and drop,
  the eight stages as they run, the result with its numbers and the EPUB
  ready to download or to read without leaving the page. It is built with
  standalone components and signals, and it talks to the API through the
  development server proxy.
- **A reader.** [foliate-js](https://github.com/johnfactotum/foliate-js)
  (MIT) behind an adapter of our own: one page or a spread, a plain or a
  book style, the type, the size, the leading, the margins and three themes,
  and the reading progress kept in the browser.
- **The reading mode.** A button takes the book to the whole screen: the
  header of the application and the toolbar of the reader disappear, the
  page keeps the window and a floating bar — faint until the pointer finds
  it — gives the progress, the contents and the way out. The browser is
  asked for the full screen, and leaving the full screen leaves the mode.
- `scan2epub resume`: continues an interrupted conversion from its cache.
- `scan2epub estimate`: the price of a run before it happens.
- `scan2epub eval`: the CER and the WER of an engine against a reference
  transcription.
- The **PaddleOCR-VL**, **TeleOCR** and **Kraken** adapters, next to
  Tesseract, behind the same `OcrEngine` port.
- An **OpenCV layout analyser**: the columns, the figures and the zones of a
  page, so a two-column scan is read in the right order.
- The **LiteLLM corrector**, behind a guardrail that accepts a correction
  only when its normalised edit distance stays below the configured
  threshold, with the rejected ones counted and the original kept.
- The cost of a run is estimated before it starts and the budget is a hard
  limit: the pipeline stops instead of spending more.
- A corpus of public-domain pages in `samples/`, with its reference
  transcription.

### Fixed
- **The notes no longer run into the text.** The notes of a page are found
  by their place — after a gap of more than a line, in the lower half of the
  page, in the type of the body or in a smaller one — so a note whose number
  the OCR lost is a note and no longer a paragraph glued to the sentence
  above it. They are set apart at the end of their chapter, and a note that
  carries no number is kept instead of being dropped.
- **A paragraph no longer continues across a wide gap.** An OCR block that
  follows a blank space of more than a line inside a page starts a paragraph
  of its own.
- **The title is the title.** The blocks of a page are classified together:
  the first block in display type that is centred and narrower than the
  measure titles the page, the byline below it is not a heading, and an
  article whose title runs to twenty words is no longer taken for body text.
- **A book without a title takes the name of its first heading**, and the
  field of the title in the interface is a suggestion, no longer a value
  taken from the name of the file.
- **A page is never wider than it is tall.** The book keeps the proportions
  of a printed page in a window of any size, in one page and in a spread.

### Added
- **The governance of the repository.** `main` is protected: no direct push,
  for anybody; the CI must be green **and** up to date; the history is
  linear; the branches are deleted after the merge; every comment of a
  review must be resolved. The branching model is described in
  `CONTRIBUTING.md`.
- `docs/roadmap.md`: the state of every phase, with what is missing.
- `SUPPORT.md`: how to get help and how to ask a good question.
- The `release.yml` workflow: it publishes the container images and creates
  the GitHub release from the changelog.
- The `codeql.yml` workflow: the static analysis of the Python code.
- `dependabot.yml`: the Python, JavaScript and GitHub Actions dependencies
  are kept up to date.
- `CODEOWNERS`: who reviews which area.
- `.gitmessage`: the template of the commit, with the sign-off.
- The configuration file of the issues, with the links to the documentation.
- Fifteen issues to work on, with the labels and the milestones.

### Fixed
- **The JSON of `scan2epub config --show` was not valid JSON** when the
  terminal was narrow: the renderer wrapped the long lines. It is printed
  without wrapping now.
- The tests no longer depend on the colours of the terminal, nor on the
  exact characters that the OCR produces: the recognition differs from one
  platform to another.
- **The cache no longer mixes languages.** The key of a cached recognition
  result now covers the settings of the engine, so a book recognised in
  English is never served again when the language changes.
- **`--lang` is no longer ignored.** The language of the command line now
  wins over the `[ocr.tesseract] lang` of the configuration file, and the
  provider section follows it.
- **The options of a provider are read.** The keys of a provider section
  (`[ocr.tesseract] lang = "spa"`) are now honoured; before, only the
  `[ocr.tesseract.options]` sub-table was taken into account, so the
  documented format was silently ignored.
- **The footnotes no longer share an identifier.** Two notes with the same
  number on different pages produced duplicate XML identifiers, which is
  invalid. The identifier is now the position of the note in the chapter, and
  a note that cannot be referenced keeps its number.
- **"Book" and "Part" are not headings any more.** A sentence such as "Book
  the tickets" turned a whole paragraph into a chapter. A structural keyword
  must now be followed by a number or by a capitalised word.
- **A word that ends with a letter is not a conjunction.** "The company" was
  treated as if it ended with the conjunction "y", so unrelated paragraphs
  were merged.
- **A note that the OCR split no longer loses its second half.** The halves
  are recognised together, so the whole note reaches the EPUB.
- The size of an uploaded PDF is now checked while it is written, instead of
  after the whole file reached the disk.
- The `<dc:creator>` of the package document no longer carries stray
  whitespace around the name.

### Added
- `scan2epub config`: writes a documented `config.toml` template, shows the
  configuration in use and reports where the file is.
- `scan2epub convert --strict`: fails when the generated EPUB does not pass
  the EPUBCheck validation.
- A configuration file with a byte order mark is read correctly.
- The version of EPUBCheck is cached, so a conversion starts the virtual
  machine only once.
- 241 tests, 90 % of coverage, including a regression test for every bug
  above.

## [0.1.0] - Unreleased

### Added
- **Phase 1 — end-to-end MVP.**
  - `scan2epub convert` command: converts a scanned PDF into a reflowable EPUB 3
    file, entirely offline, with a progress bar.
  - `scan2epub doctor` command: reports the installed engines, the available
    Tesseract languages, the configuration file and the presence of the API
    keys — never their value.
  - Nine-stage pipeline: ingest, pre-process, layout, OCR, deterministic
    cleaning, optional LLM correction, structuring, EPUB generation and
    EPUBCheck validation.
  - `pypdfium2` page source: renders the PDF at 300 dpi and detects the blank
    pages.
  - OpenCV pre-processor: deskew (Hough transform), dark frame removal,
    denoising, adaptive binarisation and margin cropping.
  - Tesseract OCR adapter with per-page caching, so a second run does not
    recognise the pages again.
  - Deterministic cleaner: removes the running heads and the folios that
    repeat across pages, rebuilds the paragraphs that the OCR split into
    lines, rejoins the words broken by a hyphen at the end of a line, merges
    the paragraphs that continue on the next page, normalises the long s
    (``ſ``) and the Latin ligatures, and marks the footnotes.
  - Hand-written EPUB 3 writer: stored ``mimetype`` entry, ``container.xml``,
    OPF package, ``nav.xhtml`` with the table of contents and the landmarks,
    one XHTML document per chapter, linked EPUB footnotes and a minimal
    stylesheet that never forces the typography of the reader.
  - EPUBCheck integration: the generated file is validated automatically and
    the report is shown with the result of the conversion.
  - Structured logging with automatic redaction of the credentials.
  - `config.toml` support with environment variable overrides.
  - 203 tests, 89 % of coverage.

### Added
- **Browser test suite** driven by Playwright and Chromium. The generated book
  is opened in a real browser and in **foliate-js**, the reference EPUB 3
  reader, and checked for reflow, working navigation, linked footnotes, and
  the metadata and table of contents that the reader builds.
- **Web interface and REST API preview.** `scan2epub serve` starts a FastAPI
  service that exposes the same pipeline over HTTP: a small web page that
  uploads a PDF, the routes `/health`, `/api/engines`, `/api/convert` and
  `/api/download`, and the OpenAPI documentation at `/docs`.
- Complete documentation: `docs/architecture.md`, `docs/adding-an-engine.md`,
  `docs/configuration.md`, `docs/usage.md`, `docs/testing.md`,
  `docs/epub-layout.md`, `docs/benchmarks.md` and `docs/naming.md`.
- Continuous integration: lint, types, tests, the licence check, the EPUBCheck
  validation of a generated book, the browser tests and the build of the CPU
  and GPU images.
- `docker/Dockerfile.cpu`, `docker/Dockerfile.gpu` and a `docker-compose.yml`
  with the `cpu`, `gpu` and `ollama` profiles.

### Changed
- The CLI and the API build the pipeline through a single factory, so an
  engine is registered once and works everywhere.

[Unreleased]: https://github.com/WassimAarab08/scan2epub/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/WassimAarab08/scan2epub/releases/tag/v0.1.0
