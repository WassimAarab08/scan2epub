"""Tests of the REST API of the queue of jobs."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scan2epub.api.app import create_app
from scan2epub.config import Config, GeneralConfig
from scan2epub.infrastructure.storage.sqlite_jobs import JobStore

pytestmark = pytest.mark.integration


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Return a test client with its own data directory."""
    monkeypatch.setenv("SCAN2EPUB_DATA_DIR", str(tmp_path / "data"))
    import scan2epub.api.app as module

    monkeypatch.setattr(module, "DATA_DIR", tmp_path / "data")
    config = Config(general=GeneralConfig(language="eng", validate_epub=False))
    return TestClient(create_app(config))


def test_the_health_check_answers(client: TestClient) -> None:
    """The service reports that it is alive."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_the_engines_are_listed(client: TestClient) -> None:
    """The engines are described."""
    response = client.get("/api/engines")
    assert response.status_code == 200
    names = [engine["name"] for engine in response.json()]
    assert "tesseract" in names


def test_a_job_is_queued(client: TestClient, sample_pdf: Path) -> None:
    """A file that is uploaded becomes a job."""
    with sample_pdf.open("rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("sample.pdf", handle, "application/pdf")},
            data={"title": "El libro"},
        )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["id"]


def test_the_engine_of_the_request_travels_with_the_job(
    client: TestClient, sample_pdf: Path
) -> None:
    """The engine chosen in the interface is the one the worker runs."""
    with sample_pdf.open("rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("sample.pdf", handle, "application/pdf")},
            data={"engine": "kraken", "language": "eng"},
        )
    assert response.status_code == 201, response.text
    store = cast("JobStore", cast("FastAPI", client.app).state.job_store)
    job = store.get(response.json()["id"])
    assert job is not None
    assert job.options["engine"] == "kraken"
    assert job.options["language"] == "eng"


def test_the_jobs_are_listed(client: TestClient, sample_pdf: Path) -> None:
    """The queue can be listed."""
    with sample_pdf.open("rb") as handle:
        client.post("/api/jobs", files={"file": ("sample.pdf", handle, "application/pdf")})
    response = client.get("/api/jobs")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_a_job_is_found(client: TestClient, sample_pdf: Path) -> None:
    """One job can be read."""
    with sample_pdf.open("rb") as handle:
        created = client.post(
            "/api/jobs", files={"file": ("sample.pdf", handle, "application/pdf")}
        ).json()
    response = client.get(f"/api/jobs/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_an_unknown_job_is_a_404(client: TestClient) -> None:
    """A job that does not exist is reported."""
    assert client.get("/api/jobs/nope").status_code == 404


def test_a_job_is_cancelled(client: TestClient, sample_pdf: Path) -> None:
    """A queued job can be cancelled."""
    with sample_pdf.open("rb") as handle:
        created = client.post(
            "/api/jobs", files={"file": ("sample.pdf", handle, "application/pdf")}
        ).json()
    response = client.delete(f"/api/jobs/{created['id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_a_job_is_resumed(client: TestClient, sample_pdf: Path) -> None:
    """A cancelled job can be put back in the queue."""
    with sample_pdf.open("rb") as handle:
        created = client.post(
            "/api/jobs", files={"file": ("sample.pdf", handle, "application/pdf")}
        ).json()
    client.delete(f"/api/jobs/{created['id']}")
    response = client.post(f"/api/jobs/{created['id']}/resume")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_the_events_of_an_unknown_job_are_a_404(client: TestClient) -> None:
    """The stream of a job that does not exist is reported."""
    assert client.get("/api/jobs/nope/events").status_code == 404


def test_the_events_are_a_stream(client: TestClient, sample_pdf: Path) -> None:
    """The progress is served as a Server-Sent Events stream."""
    with sample_pdf.open("rb") as handle:
        created = client.post(
            "/api/jobs", files={"file": ("sample.pdf", handle, "application/pdf")}
        ).json()
    with client.stream("GET", f"/api/jobs/{created['id']}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        chunk = next(response.iter_bytes())
        assert chunk is not None


def test_the_openapi_schema_describes_the_jobs(client: TestClient) -> None:
    """The API is documented."""
    schema = client.get("/openapi.json").json()
    assert "/api/jobs" in schema["paths"]
    assert "/api/jobs/{job_id}/events" in schema["paths"]
