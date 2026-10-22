# Roadmap

The plan of the project, with the state of every piece. The percentages are
honest: they measure the work that is done, not the work that is planned.

| Phase | State | What it delivers |
| --- | --- | --- |
| 0 — Repository | **100 %** | Repository, Apache-2.0 licence, documentation, CI skeleton, issue and pull request templates. |
| 1 — MVP | **100 %** | `scan2epub convert`: Tesseract → deterministic cleaning → a valid EPUB 3. |
| 2 — Local models | **90 %** | The layout analyser, the three vision-language engines, the resume and the evaluation are done; the benchmark table has no numbers yet. |
| 3 — Remote models | **75 %** | The LiteLLM corrector behind the guardrail, the modernisation, the cost estimate and the hard budget are done; a remote OCR adapter and the retries are not. |
| 4 — Service | **100 %** | The API, the SQLite queue, the worker, the progress by SSE and the endpoints to list, cancel and resume a job. |
| 5 — Web interface | **80 %** | The Angular application, the upload, the live stages and the integrated reader are done; the review view is not. |
| 6 — Release | **50 %** | The container images and the CI are done; the v0.1.0 release is not. |

## Phase 0 — Repository ✅

- [x] Apache-2.0 licence, `NOTICE`, `THIRD_PARTY_LICENSES.md`.
- [x] `README.md` in English and `README.es.md` in Spanish.
- [x] `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`.
- [x] Issue and pull request templates, `CODEOWNERS`.
- [x] The continuous integration: lint, types, tests, licences, EPUBCheck, browser tests, images.
- [x] `main` is protected: no direct push, the CI must be green.

## Phase 1 — MVP ✅

- [x] `scan2epub convert`: the whole conversion on the command line.
- [x] `scan2epub doctor`: what the installation supports.
- [x] `scan2epub config`: a documented `config.toml`.
- [x] `scan2epub serve`: the REST API and a small web page.
- [x] Ingest: `pypdfium2` at 300 dpi, the blank pages detected.
- [x] Pre-processing: deskew, removal of the scan frame, denoising, adaptive binarisation.
- [x] OCR: the Tesseract adapter, with the language data of the legacy Spanish.
- [x] Deterministic cleaning: running heads, folios, paragraphs, hyphenation, the long s, the ligatures, the footnotes.
- [x] Structure: the chapters, the table of contents, the linked footnotes.
- [x] EPUB 3 written by hand, with a stylesheet that never forces the typography.
- [x] Validation with EPUBCheck, and `--strict` to refuse an invalid book.
- [x] The cache: the artefacts are keyed by the hash of their inputs, per page.
- [x] 241 tests, 90 % of coverage, and a browser test that opens the book in foliate-js.

## Phase 2 — Local models ◕ 90 %

- [x] The cache of the recognition results, keyed by the content and by the settings of the engine.
- [x] The pre-processed images are cached too, so a second run does not redo the work.
- [x] The layout analyser: the columns, the figures and the footnote zones of a page.
- [x] The **PaddleOCR-VL** adapter (`transformers` supports it natively, without `trust_remote_code`).
- [x] The **TeleOCR** adapter, behind an explicit `--trust-remote-code` and a pinned revision.
- [x] The **Kraken** adapter, for the historical handwriting.
- [x] `scan2epub resume`: continue an interrupted job.
- [x] The corpus of `samples/`: pages of public-domain books with their reference transcription.
- [x] `scan2epub eval`: the CER and the WER of every engine, with and without the correction.
- [ ] The table of benchmarks in `docs/benchmarks.md`, with the numbers of every engine.

## Phase 3 — Remote models ◕ 75 %

- [ ] The **LiteLLM** vision adapter: any provider that speaks the OpenAI format.
- [x] The **LiteLLM** corrector, with the edit-distance guardrail and the stored diffs.
- [x] `--modernize`, off by default, to modernise the spelling.
- [x] The cost estimator and the hard budget limit.
- [ ] The retries with backoff and the rate limiting.
- [x] `scan2epub estimate`: the price of a run, before it happens.

## Phase 4 — Service ✅

- [x] The REST API: `/health`, `/api/engines`, `/api/convert`, `/api/download`.
- [x] The web page that converts a book.
- [x] The OpenAPI documentation at `/docs`.
- [x] The queue of jobs in SQLite, with an atomic claim.
- [x] The worker process.
- [x] The progress by SSE, with the events replayed to a client that arrives late.
- [x] The endpoints to list, cancel and resume the jobs.

## Phase 5 — Web interface ◕ 80 %

- [x] The Angular application, with standalone components and signals.
- [x] The drag and drop upload.
- [x] The selection of the engine and of the corrector, with the estimated cost.
- [x] The progress by stage.
- [ ] The review view: the scan and the text side by side, editable.
- [x] The integrated reader: the font, the size, the leading, the margins, the themes and the saved progress.
- [x] The reading mode: the book takes the whole screen and every menu goes away.

## Phase 6 — Release ◔ 50 %

- [x] The CPU image and the GPU image.
- [x] `docker compose up` with the `cpu`, `gpu` and `ollama` profiles.
- [x] The CI that builds the images and the one that validates the generated books.
- [ ] The `release.yml` workflow that publishes the images and the GitHub release.
- [ ] The v0.1.0 release.

## How to help

The issues labelled [`good first issue`](https://github.com/WassimAarab08/scan2epub/labels/good%20first%20issue)
are the easiest way to start. The guide
[`docs/adding-an-engine.md`](adding-an-engine.md) shows how to write an OCR
engine in fewer than fifty lines.

Everything that is not in the list above is a bug or a surprise: open an issue
with the command you ran and the output you got.
