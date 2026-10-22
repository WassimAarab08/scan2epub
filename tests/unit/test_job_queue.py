"""Tests of the queue of jobs and of the worker."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from scan2epub.api.worker import Worker, WorkerEvent, _metadata_for
from scan2epub.application.factory import with_language
from scan2epub.config import Config, GeneralConfig
from scan2epub.infrastructure.storage.sqlite_jobs import JobStatus, JobStore


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    """Return an empty queue."""
    with JobStore(tmp_path / "jobs.db") as queue:
        yield queue


def test_every_thread_gets_a_connection_of_its_own(store: JobStore) -> None:
    """The worker and the requests never share a connection.

    A connection of SQLite is not safe to use from two threads at once, and
    sharing one made the requests of the API fail at random with
    ``sqlite3.InterfaceError: bad parameter or other API misuse``.
    """
    connection = store._connection()
    seen: list[object] = []

    def other() -> None:
        seen.append(store._connection())

    thread = threading.Thread(target=other)
    thread.start()
    thread.join()

    assert seen and seen[0] is not connection


def test_the_book_takes_the_tag_of_its_language_not_the_code_of_the_ocr() -> None:
    """The book is ``es`` though Tesseract is told ``spa``.

    The code of the recognition engine is not a language tag that a reader
    understands, and putting it in ``dc:language`` made an EPUB in Spanish
    declare itself in a language that no reader knows.
    """
    config = Config(general=GeneralConfig(language="spa"))
    metadata = _metadata_for({"title": "El libro", "language": "spa"}, config, "libro")
    assert metadata.language == "es"
    assert _metadata_for({}, with_language(config, "eng"), "libro").language == "en"


def test_a_job_is_created(store: JobStore) -> None:
    """A job is queued."""
    job = store.create("libro.pdf", {"title": "Libro"})
    assert job.status is JobStatus.QUEUED
    assert store.count() == 1
    assert store.get(job.id) is not None


def test_a_job_is_claimed_atomically(store: JobStore) -> None:
    """Only one worker can claim a job."""
    store.create("libro.pdf")
    first = store.claim()
    second = store.claim()
    assert first is not None
    assert second is None
    assert store.get(first.id).status is JobStatus.RUNNING  # type: ignore[union-attr]


def test_two_workers_never_take_the_same_job(tmp_path: Path) -> None:
    """The claim is safe with several workers."""
    path = tmp_path / "jobs.db"
    with JobStore(path) as queue:
        queue.create("a.pdf")
        queue.create("b.pdf")
    claimed: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        with JobStore(path) as queue:
            while True:
                job = queue.claim()
                if job is None:
                    return
                with lock:
                    claimed.append(job.id)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert len(claimed) == 2
    assert len(set(claimed)) == 2


def test_a_job_is_finished(store: JobStore) -> None:
    """A job that succeeded is marked as done."""
    job = store.create("libro.pdf")
    store.finish(job.id, "libro.epub")
    finished = store.get(job.id)
    assert finished is not None
    assert finished.status is JobStatus.DONE
    assert finished.output == "libro.epub"
    assert finished.finished_at is not None


def test_a_job_that_failed_keeps_the_error(store: JobStore) -> None:
    """The error of a failed job is kept."""
    job = store.create("libro.pdf")
    store.fail(job.id, "it exploded")
    failed = store.get(job.id)
    assert failed is not None
    assert failed.status is JobStatus.FAILED
    assert failed.error == "it exploded"


def test_a_job_is_cancelled(store: JobStore) -> None:
    """A queued job can be cancelled."""
    job = store.create("libro.pdf")
    assert store.cancel(job.id)
    assert store.get(job.id).status is JobStatus.CANCELLED  # type: ignore[union-attr]
    # A cancelled job cannot be cancelled twice.
    assert not store.cancel(job.id)


def test_a_job_is_resumed(store: JobStore) -> None:
    """A failed job can be put back in the queue."""
    job = store.create("libro.pdf")
    store.fail(job.id, "it exploded")
    assert store.requeue(job.id)
    resumed = store.get(job.id)
    assert resumed is not None
    assert resumed.status is JobStatus.QUEUED
    assert resumed.error is None


def test_the_jobs_are_listed(store: JobStore) -> None:
    """The queue can be listed."""
    for index in range(3):
        store.create(f"{index}.pdf")
    assert len(store.list()) == 3
    assert len(store.list(limit=2)) == 2


def test_the_options_survive_the_round_trip(store: JobStore) -> None:
    """The options of a job are kept."""
    job = store.create("libro.pdf", {"title": "El libro", "author": "Anonimo"})
    stored = store.get(job.id)
    assert stored is not None
    assert stored.options["title"] == "El libro"
    assert stored.options["author"] == "Anonimo"


def test_the_worker_publishes_the_progress(store: JobStore, tmp_path: Path) -> None:
    """The worker publishes the events of the job."""
    worker = Worker(store, Config(), work_dir=tmp_path / "work")
    worker.publish(WorkerEvent("abc", "ocr", "recognising", page=1, total=3, percent=33.0))
    events = worker.drain()
    assert len(events) == 1
    assert events[0].stage == "ocr"
    assert events[0].as_dict()["percent"] == 33.0


def test_the_worker_runs_a_job(store: JobStore, sample_pdf: Path, tmp_path: Path) -> None:
    """The worker converts a book and marks the job as done."""
    job = store.create(
        str(sample_pdf),
        {"title": "El libro", "output": str(tmp_path / "out.epub")},
    )
    worker = Worker(store, Config(), work_dir=tmp_path / "work")
    worker.run_once()
    finished = store.get(job.id)
    assert finished is not None
    assert finished.status is JobStatus.DONE
    assert (tmp_path / "out.epub").is_file()


def test_a_job_that_fails_is_marked_as_failed(store: JobStore, tmp_path: Path) -> None:
    """A job that cannot run is marked as failed, not lost."""
    job = store.create(str(tmp_path / "missing.pdf"), {"output": str(tmp_path / "out.epub")})
    worker = Worker(store, Config(), work_dir=tmp_path / "work")
    worker.run_once()
    failed = store.get(job.id)
    assert failed is not None
    assert failed.status is JobStatus.FAILED
    assert failed.error


def test_the_worker_stops(store: JobStore, tmp_path: Path) -> None:
    """The worker stops when it is asked to."""
    worker = Worker(store, Config(), work_dir=tmp_path / "work", poll_interval=0.01)
    worker.stop()
    thread = threading.Thread(target=worker.run_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    thread.join(timeout=5)
    assert not thread.is_alive()
