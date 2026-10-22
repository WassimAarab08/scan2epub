# The service and the web interface

Two processes make the service: the API, which owns the queue and the
conversion, and the Angular application, which owns the screens and the
reader.

```bash
# 1. The API, the queue and the worker.
uv run scan2epub serve --host 127.0.0.1 --port 8000

# 2. The application, in a second terminal.
cd web
npm install
npm start          # http://127.0.0.1:4200
```

The development server proxies `/api`, `/health` and `/openapi.json` to
`http://127.0.0.1:8000`, so the page talks to the API on its own origin and
no CORS rule is needed. In production, `web/dist/web` is served by the same
container as the API, at `/`.

## Why a queue and not one long request

A long book takes minutes, and a browser, a proxy or a mobile network drops a
request that stays silent for that long. The conversion is therefore a job:
see below for the two calls and the stream that joins them.

The job is stored in SQLite (`SCAN2EPUB_DATABASE`, by default
`.scan2epub/jobs.db`) and claimed atomically by the worker, so two workers
never run the same job. A job that was interrupted is queued again with
`POST /api/jobs/{id}/resume`: the per-page cache makes it start from the last
page it recognised instead of from the first one.

The stream replays the events that were published before the client
connected. A browser that reloads in the middle of a conversion therefore
sees the whole history, not just what happens next.

```
POST /api/jobs ──▶ 201 {"id": "…", "status": "queued"}
GET  /api/jobs/{id}/events ──▶ text/event-stream
                                event: ocr
                                data: {"stage": "ocr", "page": 12, "total": 320, …}
                                …
                                event: done
                                data: {"summary": {…, "download": "/api/download/…"}}
```

### The endpoints

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/health` | The version and the engines that are installed. |
| `GET` | `/api/engines` | Every engine, with whether it can be used and why. |
| `POST` | `/api/jobs` | Queue a conversion. `multipart/form-data`: `file`, `title`, `author`, `year`, `language`, `engine`. |
| `GET` | `/api/jobs` | The jobs, newest first. |
| `GET` | `/api/jobs/{id}` | The state of a job and its summary. |
| `GET` | `/api/jobs/{id}/events` | The progress of a job, as Server-Sent Events. |
| `DELETE` | `/api/jobs/{id}` | Cancel a job. |
| `POST` | `/api/jobs/{id}/resume` | Queue an interrupted or failed job again. |
| `GET` | `/api/download/{job}/{name}` | The generated EPUB. |
| `POST` | `/api/convert` | The blocking conversion, kept for scripts. |

An empty `title` is not a mistake: the structure stage titles the book with
the first heading of the document. An empty `engine` means the engine of the
configuration file.

The OpenAPI document is at `/docs` and `/openapi.json`.

## The application

The page has three states: the form, the run and the result.

- **The form** asks for the PDF (by drop or by picker), the language of the
  scan, the engine, and optionally the title, the author and the year. The
  name of the file is offered as a placeholder, never as a value: the book
  usually knows its own title better than the name of a download does.
- **The run** shows the eight stages with the page it is on, the elapsed
  time and the estimated cost when the engine is a paid one. The stages come
  from the stream, not from a timer.
- **The result** shows the numbers of the conversion — pages, chapters,
  notes, the fixed hyphens, the running heads and the folios that were
  removed — and offers the EPUB for download or for reading in place.

The application keeps its state in signals: `ConversionStore` for the form
and the run, `ReaderStore` for the preferences of the reader.

## The reader

The reader is [foliate-js](https://github.com/johnfactotum/foliate-js) (MIT),
vendored under `web/src/assets/foliate-js/`, behind an adapter of our own
(`features/reader/foliate.ts`). A dynamic import loads the library the first
time a book is opened, so it never weighs on the first page.

| Control | What it does |
| --- | --- |
| One page / Two pages | Changes `max-column-count`; the spread is the default on a wide window. |
| Plain / Book | `plain` leaves the text as it is; `book` justifies it, hyphenates it and marks the paragraphs with an indent. |
| Typeface, size, leading, margin | The book reflows at once; the settings are kept in `localStorage`. |
| Light, dark, sepia | The theme of the page, the header and the book. |
| Contents | The table of contents of the EPUB. |
| Reading mode | See below. |

The page keeps the proportions of a printed page: its width follows the
height of the window (`56dvh` for a page, `112dvh` for a spread), so a page
is never wider than it is tall, whatever the window.

The progress is saved as an EPUB CFI, so a reader who comes back finds the
exact paragraph where they left.

### The reading mode

A button in the toolbar of the reader asks the browser for the full screen
and hides everything else: the header of the application, the toolbar of the
reader, the margins of the page. The book keeps the window.

A floating bar, faint until the pointer finds it, gives the percentage, the
contents and the way out. Esc — or the button — leaves the full screen, and
leaving the full screen leaves the mode, so the browser and the page never
disagree about what is on the screen.

The mode is a preference like the others: it survives a reload.

## Keys, secrets and local data

The API reads its keys from the environment (`OPENAI_API_KEY` and the ones
that LiteLLM knows), never from the request and never from the database. The
uploads and the results live under `SCAN2EPUB_DATA_DIR` (`.scan2epub` by
default). The reading preferences and the progress never leave the browser:
they are kept in the `localStorage` of the page.
