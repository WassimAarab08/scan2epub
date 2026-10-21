"""Tests of the REST API."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scan2epub.api.app import create_app
from scan2epub.config import Config, GeneralConfig

pytestmark = pytest.mark.integration


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return the directory where the uploads are written."""
    target = tmp_path / "data"
    target.mkdir()
    monkeypatch.setenv("SCAN2EPUB_DATA_DIR", str(target))
    import scan2epub.api.app as module

    monkeypatch.setattr(module, "DATA_DIR", target)
    return target


@pytest.fixture
def client(data_dir: Path, require_tesseract: None) -> TestClient:
    """Return a test client of the API."""
    config = Config(general=GeneralConfig(language="eng", validate_epub=False))
    return TestClient(create_app(config))


def test_the_health_check_answers(client: TestClient) -> None:
    """The service reports that it is alive."""
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "tesseract" in payload["engines"]


def test_the_engines_are_listed(client: TestClient) -> None:
    """The available engines are described."""
    response = client.get("/api/engines")
    assert response.status_code == 200
    engines = response.json()
    assert engines[0]["name"] == "tesseract"


def test_the_landing_page_is_served(client: TestClient) -> None:
    """The root of the service is a small web interface."""
    response = client.get("/")
    assert response.status_code == 200
    assert "scan2epub" in response.text
    assert "/api/convert" in response.text


def test_a_pdf_is_converted(client: TestClient, sample_pdf: Path) -> None:
    """A file that is uploaded is converted and can be downloaded."""
    with sample_pdf.open("rb") as handle:
        response = client.post(
            "/api/convert",
            files={"file": ("sample.pdf", handle, "application/pdf")},
            data={"title": "El libro", "author": "Anonimo", "lang": "eng"},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["title"] == "El libro"
    assert payload["pages"] == 3
    assert payload["chapters"] >= 1
    assert payload["size"] > 0
    assert "HISTORIA DE LA IMPRENTA" in payload["removed_running_heads"]

    download = client.get(payload["download"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/epub+zip"
    assert download.content[:2] == b"PK"


def test_a_file_that_is_not_a_pdf_is_refused(client: TestClient) -> None:
    """Only PDFs are accepted."""
    response = client.post(
        "/api/convert",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_an_empty_file_is_refused(client: TestClient) -> None:
    """An empty upload is an error."""
    response = client.post(
        "/api/convert",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400


def test_a_path_that_tries_to_escape_is_refused(client: TestClient) -> None:
    """The download route does not allow to escape the data directory."""
    response = client.get("/api/download/..%2F..%2Fetc/passwd")
    assert response.status_code in {400, 404}


def test_the_openapi_schema_is_served(client: TestClient) -> None:
    """The API is documented."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/api/convert" in schema["paths"]
    assert os.environ.get("SCAN2EPUB_DATA_DIR")
