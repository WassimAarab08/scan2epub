# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffolding: repository layout, Apache-2.0 license, contribution
  guidelines, code of conduct, security policy and issue/PR templates.

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
  - 136 tests, 88 % of coverage.

[Unreleased]: https://github.com/WassimAarab08/scan2epub/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/WassimAarab08/scan2epub/releases/tag/v0.1.0
