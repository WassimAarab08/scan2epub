"""The REST API.

The API exposes the same pipeline as the command line. It is deliberately
small: the jobs are executed in the process that receives them, which is
enough for a single-user installation. The queue and the worker process
arrive in Phase 4.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from scan2epub import __version__
from scan2epub.application.factory import available_engines, build_pipeline, with_language
from scan2epub.config import Config, load_config
from scan2epub.domain.models import BookMetadata
from scan2epub.errors import Scan2EpubError

__all__ = ["create_app"]

#: The largest PDF the API accepts, in bytes.
MAX_UPLOAD_BYTES = 512 * 1024 * 1024

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
  result.textContent = 'Converting… this can take a while.';
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

    app = FastAPI(
        title="scan2epub",
        version=__version__,
        summary="Turn scanned public-domain books into clean, reflowable EPUB 3.",
        description=(
            "The whole conversion runs locally. No API key and no network "
            "access are needed for the default engine."
        ),
    )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Report that the service is alive."""
        return HealthResponse(engines=list(available_engines()))

    @app.get("/api/engines", response_model=list[EngineInfo], tags=["system"])
    def engines() -> list[EngineInfo]:
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
        if file.content_type not in {
            "application/pdf",
            "application/octet-stream",
            "binary/octet-stream",
        }:
            raise HTTPException(status_code=415, detail="The file must be a PDF.")

        stem = Path(file.filename or "libro").stem[:80]
        work = Path(tempfile.mkdtemp(prefix="scan2epub-", dir=str(DATA_DIR)))
        source = work / f"{stem}.pdf"
        output = work / f"{stem}.epub"

        with source.open("wb") as handle:
            shutil.copyfileobj(file.file, handle, length=1024 * 1024)
        if source.stat().st_size > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="The file is too large.")
        if source.stat().st_size == 0:
            raise HTTPException(status_code=400, detail="The file is empty.")

        try:
            effective = with_language(settings, language) if language else settings

            pipeline = build_pipeline(
                effective,
                source,
                work / "work",
                cache_dir=work / "cache",
            )
            metadata = BookMetadata(
                title=title or stem.replace("_", " ").replace("-", " ").strip() or "Libro",
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
            title=metadata.title,
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

    @app.get("/api/download/{job}/{name}", tags=["conversion"])
    def download(job: str, name: str) -> Response:
        """Serve a generated EPUB."""
        if "/" in job or "/" in name or ".." in job or ".." in name:
            raise HTTPException(status_code=400, detail="Invalid path.")
        path = (DATA_DIR / job / name).resolve()
        if not path.is_file() or DATA_DIR.resolve() not in path.parents:
            raise HTTPException(status_code=404, detail="The file was not found.")
        return Response(
            content=path.read_bytes(),
            media_type="application/epub+zip",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.exception_handler(Scan2EpubError)
    def handle_scan2epub_error(
        request: Any,  # noqa: ARG001, ANN401 - the signature is imposed by FastAPI
        exc: Scan2EpubError,
    ) -> JSONResponse:
        """Turn the errors of the library into clear answers."""
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app
