"""The REST API.

The API exposes the same pipeline as the command line. It is deliberately
small: the jobs are executed in the process that receives them, which is
enough for a single-user installation. The queue and the worker process
arrive in Phase 4.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from scan2epub import __version__
from scan2epub.api.worker import Worker
from scan2epub.application.factory import available_engines, build_pipeline, with_language
from scan2epub.config import Config, load_config
from scan2epub.domain.models import BookMetadata
from scan2epub.errors import Scan2EpubError
from scan2epub.infrastructure.storage.sqlite_jobs import Job, JobStore

__all__ = ["create_app"]

#: The largest PDF the API accepts, in bytes.
MAX_UPLOAD_BYTES = 512 * 1024 * 1024

#: The content types that are accepted for an upload.
ACCEPTED_TYPES = frozenset(
    {
        "application/pdf",
        "application/octet-stream",
        "binary/octet-stream",
    }
)

#: The directories where the uploads and the results are written.
DATA_DIR = Path(os.environ.get("SCAN2EPUB_DATA_DIR", ".scan2epub"))


class HealthResponse(BaseModel):
    """The answer of the health check."""

    status: str = "ok"
    version: str = __version__
    engines: list[str] = Field(default_factory=list)


class EngineInfo(BaseModel):
    """The description of an OCR engine."""

    name: str
    available: bool
    details: str = ""


class ConvertResponse(BaseModel):
    """The summary of a conversion."""

    title: str
    pages: int
    chapters: int
    size: int
    duration_seconds: float
    removed_running_heads: list[str] = Field(default_factory=list)
    removed_page_numbers: int = 0
    joined_hyphens: int = 0
    merged_paragraphs: int = 0
    footnotes: int = 0
    epub_valid: bool = True
    epub_warnings: list[str] = Field(default_factory=list)
    download: str = ""


class JobResponse(BaseModel):
    """The state of a job of the queue."""

    id: str
    status: str
    created_at: str = ""
    updated_at: str = ""
    error: str | None = None
    download: str | None = None
    summary: dict[str, Any] | None = None


def _index_page() -> str:
    """Return the landing page of the API."""
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>scan2epub</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 16px/1.6 system-ui, sans-serif; margin: 0; padding: 3rem 1.5rem;
         max-width: 44rem; margin-inline: auto; }
  h1 { font-size: 1.6rem; margin: 0 0 .3rem; }
  p.lead { margin: 0 0 2rem; opacity: .75; }
  form { display: grid; gap: 1rem; }
  label { font-weight: 600; font-size: .9rem; }
  input, select, button { font: inherit; padding: .55rem .7rem; border-radius: .4rem;
                          border: 1px solid rgba(128,128,128,.45); background: transparent;
                          color: inherit; }
  button { background: #2f6f4f; color: #fff; border: 0; font-weight: 600; cursor: pointer; }
  button:disabled { opacity: .6; cursor: progress; }
  .result { margin-top: 2rem; padding: 1rem; border-radius: .5rem;
            background: rgba(128,128,128,.12); }
  code { font-size: .85em; opacity: .8; }
</style></head><body>
<h1>scan2epub</h1>
<p class="lead">Turn a scanned book into a clean, reflowable EPUB 3.</p>
<form id="form">
  <div>
    <label for="file">The scanned PDF</label>
    <input id="file" name="file" type="file" accept="application/pdf" required>
  </div>
  <div>
    <label for="title">Title</label>
    <input id="title" name="title" type="text" placeholder="The name of the book">
  </div>
  <div>
    <label for="author">Author</label>
    <input id="author" name="author" type="text">
  </div>
  <div>
    <label for="lang">OCR language</label>
    <select id="lang" name="lang">
      <option value="spa">Spanish (modern)</option>
      <option value="spa_old">Spanish (before 1900)</option>
      <option value="spa+spa_old">Spanish (both)</option>
      <option value="eng">English</option>
      <option value="fra">French</option>
      <option value="deu">German</option>
    </select>
  </div>
  <button type="submit" id="submit">Convert</button>
</form>
<div class="result" id="result" hidden></div>
<script>
document.getElementById('form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.getElementById('submit');
  const result = document.getElementById('result');
  button.disabled = true;
  result.hidden = false;
  result.textContent = 'Converting... this can take a while.';
  const data = new FormData(event.target);
  try {
    const response = await fetch('/api/convert', {method: 'POST', body: data});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'The conversion failed.');
    result.innerHTML = `<strong>${payload.title}</strong><br>
      ${payload.pages} pages, ${payload.chapters} chapters, ${(payload.size/1024).toFixed(1)} KiB.
      <br>Removed running heads: ${payload.removed_running_heads.join(', ') || 'none'}.<br>
      <a href="${payload.download}">Download the EPUB</a>`;
  } catch (error) {
    result.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
</script>
</body></html>
"""


def _health() -> HealthResponse:
    """Report that the service is alive."""
    return HealthResponse(engines=list(available_engines()))


def _engines() -> list[EngineInfo]:
    """List the OCR engines and whether they can be used."""
    from scan2epub.infrastructure.ocr.tesseract import (  # noqa: PLC0415
        available_languages,
        tesseract_version,
    )

    version = tesseract_version()
    languages = available_languages()
    return [
        EngineInfo(
            name="tesseract",
            available=version is not None,
            details=(
                f"version {version}, languages: {', '.join(languages)}"
                if version
                else "not installed"
            ),
        )
    ]


def _store_upload(file: UploadFile, target: Path) -> None:
    """Write the uploaded file, refusing the ones that are too large."""
    with target.open("wb") as handle:
        # The size is checked while the file is written, so an oversized
        # upload never fills the disk.
        written = 0
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="The file is too large.")
            handle.write(chunk)
    if target.stat().st_size == 0:
        raise HTTPException(status_code=400, detail="The file is empty.")


def _convert(
    settings: Config,
    file: UploadFile,
    title: str | None,
    author: str | None,
    year: str | None,
    language: str | None,
) -> ConvertResponse:
    """Convert an uploaded PDF and return the summary of the result."""
    if file.content_type not in ACCEPTED_TYPES:
        raise HTTPException(status_code=415, detail="The file must be a PDF.")

    stem = Path(file.filename or "libro").stem[:80]
    work = Path(tempfile.mkdtemp(prefix="scan2epub-", dir=str(DATA_DIR)))
    source = work / f"{stem}.pdf"
    output = work / f"{stem}.epub"
    _store_upload(file, source)

    try:
        effective = with_language(settings, language) if language else settings
        pipeline = build_pipeline(
            effective,
            source,
            work / "work",
            cache_dir=work / "cache",
        )
        metadata = BookMetadata(
            title=title or "",
            author=author or "",
            language=effective.general.output_language or effective.general.language or "es",
            year=year,
        )
        result = pipeline.run(metadata, output)
    except HTTPException:
        raise
    except Scan2EpubError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"The conversion failed: {exc}") from exc

    return ConvertResponse(
        title=result.book.metadata.title or metadata.title,
        pages=result.page_count,
        chapters=len(result.book.chapters),
        size=result.epub_size,
        duration_seconds=round(result.duration_seconds, 2),
        removed_running_heads=list(result.clean.removed_running_heads),
        removed_page_numbers=result.clean.removed_page_numbers,
        joined_hyphens=result.clean.joined_hyphens,
        merged_paragraphs=result.clean.merged_paragraphs,
        footnotes=result.clean.detected_footnotes,
        epub_valid=result.validation.passed,
        epub_warnings=list(result.validation.warnings),
        download=f"/api/download/{work.name}/{output.name}",
    )


def _download(job: str, name: str) -> Response:
    """Serve a generated EPUB.

    The names in the URL are only compared with the names on the disk: the
    path is built from the directory listing, never from the request, so a
    name such as ".." has no way of leaving the data directory.
    """
    base = DATA_DIR.resolve()
    directory = next(
        (entry for entry in base.iterdir() if entry.is_dir() and entry.name == job),
        None,
    )
    if directory is None:
        raise HTTPException(status_code=404, detail="The file was not found.")
    path = next(
        (entry for entry in directory.iterdir() if entry.is_file() and entry.name == name),
        None,
    )
    if path is None:
        raise HTTPException(status_code=404, detail="The file was not found.")
    return Response(
        content=path.read_bytes(),
        media_type="application/epub+zip",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


def create_app(config: Config | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        config: The configuration to use. When omitted, it is read from the
            environment.

    Returns:
        The application.
    """
    settings = config or load_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    store = JobStore(Path(os.environ.get("SCAN2EPUB_DATABASE", str(DATA_DIR / "jobs.db"))))
    worker = Worker(store, settings, work_dir=DATA_DIR / "work")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        """Run the worker and close the database when the service stops."""
        thread = worker.start()
        try:
            yield
        finally:
            worker.stop()
            thread.join(timeout=5)
            store.close()

    app = FastAPI(
        title="scan2epub",
        version=__version__,
        summary="Turn scanned public-domain books into clean, reflowable EPUB 3.",
        description=(
            "The whole conversion runs locally. No API key and no network "
            "access are needed for the default engine."
        ),
        lifespan=lifespan,
    )
    app.state.job_store = store
    app.state.worker = worker

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Report that the service is alive."""
        return _health()

    @app.get("/api/engines", response_model=list[EngineInfo], tags=["system"])
    def engines() -> list[EngineInfo]:
        """List the OCR engines and whether they can be used."""
        return _engines()

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> HTMLResponse:
        """Return the landing page."""
        return HTMLResponse(_index_page())

    @app.post("/api/convert", response_model=ConvertResponse, tags=["conversion"])
    async def convert(
        file: Annotated[UploadFile, File(description="The scanned PDF.")],
        title: Annotated[str | None, Form()] = None,
        author: Annotated[str | None, Form()] = None,
        year: Annotated[str | None, Form()] = None,
        language: Annotated[str | None, Form()] = None,
    ) -> ConvertResponse:
        """Convert a scanned PDF into an EPUB and return the summary.

        The file is stored under the data directory and the EPUB can be
        downloaded from the link in the answer.
        """
        return _convert(settings, file, title, author, year, language)

    @app.get("/api/download/{job}/{name}", tags=["conversion"])
    def download(job: str, name: str) -> Response:
        """Serve a generated EPUB."""
        return _download(job, name)

    @app.post("/api/jobs", response_model=JobResponse, status_code=201, tags=["jobs"])
    def create_job(
        file: Annotated[UploadFile, File(description="The scanned PDF.")],
        title: Annotated[str | None, Form()] = None,
        author: Annotated[str | None, Form()] = None,
        year: Annotated[str | None, Form()] = None,
        language: Annotated[str | None, Form()] = None,
    ) -> JobResponse:
        """Queue a conversion and return the job.

        The answer comes back at once: the work is done in the background and
        the progress is published on the stream of the events of the job.
        """
        if file.content_type not in ACCEPTED_TYPES:
            raise HTTPException(status_code=415, detail="The file must be a PDF.")
        stem = Path(file.filename or "libro").stem[:80]
        staging = Path(tempfile.mkdtemp(prefix="scan2epub-", dir=str(DATA_DIR)))
        source = staging / f"{stem}.pdf"
        _store_upload(file, source)

        job = store.create(
            str(source),
            {
                "title": title or "",
                "author": author or "",
                "year": year,
                "language": language or settings.general.language,
            },
        )
        # The file is moved under the directory of the job, so that the link
        # of the download points at it.
        home = DATA_DIR / job.id
        home.mkdir(parents=True, exist_ok=True)
        final_source = home / f"{stem}.pdf"
        source.replace(final_source)
        output = home / f"{stem}.epub"
        options = {
            "title": title or "",
            "author": author or "",
            "year": year,
            "language": language or settings.general.language,
            "source": str(final_source),
            "output": str(output),
        }
        store.update(job.id, source=str(final_source), options=options)
        return JobResponse(
            id=job.id,
            status=job.status.value,
            created_at=job.created_at,
            download=f"/api/download/{job.id}/{output.name}",
        )

    _register_job_routes(app, store, worker)

    @app.exception_handler(Scan2EpubError)
    def handle_scan2epub_error(
        request: Any,  # noqa: ARG001, ANN401 - the signature is imposed by FastAPI
        exc: Scan2EpubError,
    ) -> JSONResponse:
        """Turn the errors of the library into clear answers."""
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app


def _register_job_routes(app: FastAPI, store: JobStore, worker: Worker) -> None:
    """Register the routes of the queue of jobs."""

    @app.get("/api/jobs", response_model=list[JobResponse], tags=["jobs"])
    def list_jobs(limit: Annotated[int, Query(ge=1, le=500)] = 50) -> list[JobResponse]:
        """List the jobs, the newest first."""
        return [_job_response(job) for job in store.list(limit)]

    @app.get("/api/jobs/{job_id}", response_model=JobResponse, tags=["jobs"])
    def get_job(job_id: str) -> JobResponse:
        """Return one job."""
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="The job was not found.")
        return _job_response(job)

    @app.delete("/api/jobs/{job_id}", response_model=JobResponse, tags=["jobs"])
    def cancel_job(job_id: str) -> JobResponse:
        """Cancel a job."""
        if not store.cancel(job_id):
            raise HTTPException(status_code=409, detail="The job cannot be cancelled.")
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="The job was not found.")
        return _job_response(job)

    @app.post("/api/jobs/{job_id}/resume", response_model=JobResponse, tags=["jobs"])
    def resume_job(job_id: str) -> JobResponse:
        """Put a job back in the queue."""
        if not store.requeue(job_id):
            raise HTTPException(status_code=409, detail="The job cannot be resumed.")
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="The job was not found.")
        return _job_response(job)

    @app.get("/api/jobs/{job_id}/events", tags=["jobs"])
    def job_events(job_id: str) -> StreamingResponse:
        """Stream the progress of a job with Server-Sent Events."""
        if store.get(job_id) is None:
            raise HTTPException(status_code=404, detail="The job was not found.")
        return StreamingResponse(
            _event_stream(worker, job_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


def _job_response(job: Job) -> JobResponse:
    """Build the answer of a job."""
    output = job.output
    download = f"/api/download/{job.id}/{Path(output).name}" if output else None
    return JobResponse(
        id=job.id,
        status=job.status.value,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
        download=download,
        summary=_complete_summary(job.summary, download, job.options),
    )


def _complete_summary(
    summary: dict[str, Any] | None,
    download: str | None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Add the title and the link of the download to the summary of a job.

    Args:
        summary: The numbers of the conversion.
        download: The link of the EPUB.
        options: The options of the job, where the title is.

    Returns:
        The summary, ready to be shown by the interface.
    """
    if summary is None:
        return None
    complete = dict(summary)
    title = (options or {}).get("title")
    if isinstance(title, str) and title:
        complete["title"] = title
    if download:
        complete["download"] = download
    return complete


async def _event_stream(worker: Worker, job_id: str) -> AsyncIterator[str]:
    """Yield the events of a job, as a Server-Sent Events stream.

    The events that were published before the client connected are sent
    first, so no progress is ever lost. The stream ends when the job is
    finished.
    """
    sent = 0
    heartbeat = 0
    while True:
        events = worker.events_for(job_id)
        for event in events[sent:]:
            data = event.as_dict()
            if event.stage == "done":
                output = data.get("output")
                download = f"/api/download/{job_id}/{Path(str(output)).name}" if output else None
                raw_summary = data.get("summary")
                summary = (
                    cast("dict[str, Any]", raw_summary) if isinstance(raw_summary, dict) else None
                )
                data["summary"] = _complete_summary(summary, download)
            yield f"event: {event.stage}\ndata: {json.dumps(data)}\n\n"
        sent = len(events)
        if any(event.stage in {"done", "error"} for event in events):
            return
        heartbeat += 1
        if heartbeat % 15 == 0:
            yield ": heartbeat\n\n"
        await asyncio.sleep(0.5)
