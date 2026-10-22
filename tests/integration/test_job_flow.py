"""Tests of the whole job flow: the upload, the worker and the download."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scan2epub.api.app import create_app
from scan2epub.config import Config, GeneralConfig

pytestmark = pytest.mark.integration


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Return a test client with its own data directory."""
    monkeypatch.setenv("SCAN2EPUB_DATA_DIR", str(tmp_path / "data"))
    import scan2epub.api.app as module

    monkeypatch.setattr(module, "DATA_DIR", tmp_path / "data")
    config = Config(general=GeneralConfig(language="eng", validate_epub=False))
    with TestClient(create_app(config)) as test_client:
        yield test_client


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 120.0) -> dict[str, object]:
    """Wait until the job is finished and return its state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = client.get(f"/api/jobs/{job_id}").json()
        if payload["status"] in {"done", "failed", "cancelled"}:
            return payload
        time.sleep(0.2)
    raise AssertionError(f"the job {job_id} did not finish in {timeout} seconds")


def test_the_worker_picks_the_job_up(client: TestClient, sample_pdf: Path) -> None:
    """The worker of the service converts the job that the API queues."""
    with sample_pdf.open("rb") as handle:
        created = client.post(
            "/api/jobs",
            files={"file": ("sample.pdf", handle, "application/pdf")},
            data={"title": "El libro", "language": "eng"},
        )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    state = _wait_for_job(client, job_id)
    assert state["status"] == "done", state
    assert state["error"] is None


def test_the_job_carries_the_numbers_of_the_conversion(
    client: TestClient, sample_pdf: Path
) -> None:
    """The summary of the conversion is kept with the job."""
    with sample_pdf.open("rb") as handle:
        created = client.post(
            "/api/jobs",
            files={"file": ("sample.pdf", handle, "application/pdf")},
            data={"title": "El libro", "language": "eng"},
        ).json()

    state = _wait_for_job(client, created["id"])
    summary = state["summary"]
    assert isinstance(summary, dict)
    assert summary["pages"] == 3
    assert summary["chapters"] >= 1
    assert summary["size"] > 0
    assert summary["duration_seconds"] >= 0


def test_the_epub_of_a_job_can_be_downloaded(client: TestClient, sample_pdf: Path) -> None:
    """The link of the download points at the file that was written."""
    with sample_pdf.open("rb") as handle:
        created = client.post(
            "/api/jobs",
            files={"file": ("sample.pdf", handle, "application/pdf")},
            data={"title": "El libro", "language": "eng"},
        ).json()

    state = _wait_for_job(client, created["id"])
    download = state["download"]
    assert download
    response = client.get(download)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/epub+zip"
    assert len(response.content) > 0


def test_the_stream_of_events_ends_with_the_result(client: TestClient, sample_pdf: Path) -> None:
    """The stream of the progress tells the browser that the job is over."""
    with sample_pdf.open("rb") as handle:
        created = client.post(
            "/api/jobs",
            files={"file": ("sample.pdf", handle, "application/pdf")},
            data={"title": "El libro", "language": "eng"},
        ).json()

    with client.stream("GET", f"/api/jobs/{created['id']}/events") as response:
        body = "".join(chunk.decode("utf-8") for chunk in response.iter_bytes())

    assert "event: done" in body
    assert "event: ocr" in body
