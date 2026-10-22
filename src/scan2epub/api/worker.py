"""The worker of the queue.

The worker polls the queue, claims a job and runs the pipeline on it. The
progress is published on a queue of events, that the API streams to the
browser with Server-Sent Events.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scan2epub.application.factory import build_pipeline, with_language
from scan2epub.application.pipeline import PipelineResult
from scan2epub.application.progress import ProgressEvent, ProgressReporter
from scan2epub.config import Config
from scan2epub.domain.models import BookMetadata
from scan2epub.infrastructure.storage.sqlite_jobs import Job, JobStatus, JobStore
from scan2epub.logging import get_logger

__all__ = ["Worker", "WorkerEvent"]

_LOGGER = get_logger(__name__)

#: The number of events that are kept for every job.
_MAX_EVENTS_PER_JOB = 500


def _empty_payload() -> dict[str, Any]:
    """Return an empty payload."""
    return {}


def _summary_of(result: PipelineResult, fallback_title: str = "") -> dict[str, Any]:
    """Build the summary of a conversion, the one the interface shows.

    Args:
        result: The result of the pipeline.
        fallback_title: The title to show when the book has none.

    Returns:
        A table with the same fields as the answer of ``POST /api/convert``.
    """
    return {
        "title": result.book.metadata.title or fallback_title,
        "pages": result.page_count,
        "chapters": len(result.book.chapters),
        "size": result.epub_size,
        "duration_seconds": round(result.duration_seconds, 2),
        "removed_running_heads": list(result.clean.removed_running_heads),
        "removed_page_numbers": result.clean.removed_page_numbers,
        "joined_hyphens": result.clean.joined_hyphens,
        "merged_paragraphs": result.clean.merged_paragraphs,
        "footnotes": result.clean.detected_footnotes,
        "epub_valid": result.validation.passed,
        "epub_warnings": list(result.validation.warnings),
    }


@dataclass(frozen=True, slots=True)
class WorkerEvent:
    """An event of the worker."""

    job_id: str
    stage: str
    message: str = ""
    page: int | None = None
    total: int | None = None
    percent: float = 0.0
    payload: dict[str, Any] = field(default_factory=_empty_payload)

    def as_dict(self) -> dict[str, Any]:
        """Return the event as a dictionary, for the SSE stream."""
        data: dict[str, Any] = {
            "job_id": self.job_id,
            "stage": self.stage,
            "message": self.message,
            "percent": self.percent,
        }
        if self.page is not None:
            data["page"] = self.page
        if self.total is not None:
            data["total"] = self.total
        data.update(self.payload)
        return data


class Worker:
    """Run the jobs of the queue, one at a time."""

    def __init__(
        self,
        store: JobStore,
        config: Config,
        *,
        work_dir: Path | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        """Initialise the worker.

        Args:
            store: The queue of jobs.
            config: The configuration of the conversions.
            work_dir: Where the intermediate files are written.
            poll_interval: The time between two polls of the queue.
        """
        self.store = store
        self.config = config
        self.work_dir = work_dir or (config.cache_directory / "work")
        self.poll_interval = poll_interval
        self.events: queue.Queue[WorkerEvent] = queue.Queue()
        # The events are also kept per job, so that a client that connects
        # late still receives the whole progress of the run.
        self._history: dict[str, list[WorkerEvent]] = {}
        self._stop = threading.Event()

    def stop(self) -> None:
        """Ask the worker to stop after the current job."""
        self._stop.set()

    def publish(self, event: WorkerEvent) -> None:
        """Publish an event of the progress."""
        self.events.put(event)
        history = self._history.setdefault(event.job_id, [])
        history.append(event)
        if len(history) > _MAX_EVENTS_PER_JOB:
            del history[: len(history) - _MAX_EVENTS_PER_JOB]

    def events_for(self, job_id: str) -> list[WorkerEvent]:
        """Return the events of a job, the oldest first."""
        return list(self._history.get(job_id, ()))

    def drain(self) -> list[WorkerEvent]:
        """Return the events that were published, without waiting."""
        events: list[WorkerEvent] = []
        while True:
            try:
                events.append(self.events.get_nowait())
            except queue.Empty:
                return events

    def run_once(self) -> Job | None:
        """Claim a job and run it.

        Returns:
            The job that was run, or ``None`` when the queue was empty.
        """
        job = self.store.claim()
        if job is None:
            return None
        self.publish(WorkerEvent(job.id, "start", "The conversion has started"))
        try:
            output, summary = self._convert(job)
        except Exception as exc:
            _LOGGER.exception("job.failed", job=job.id, error=str(exc))
            self.store.fail(job.id, str(exc))
            self.publish(WorkerEvent(job.id, "error", str(exc)))
            return job
        self.store.finish(job.id, str(output), summary)
        self.publish(
            WorkerEvent(
                job.id,
                "done",
                "The conversion has finished",
                percent=100.0,
                payload={"output": str(output), "summary": summary},
            )
        )
        return job

    def start(self) -> threading.Thread:
        """Run the worker in a background thread.

        Returns:
            The thread that polls the queue.
        """
        thread = threading.Thread(target=self.run_forever, name="scan2epub-worker", daemon=True)
        thread.start()
        return thread

    def run_forever(self) -> None:
        """Poll the queue until the worker is stopped."""
        while not self._stop.is_set():
            job = self.run_once()
            if job is None:
                time.sleep(self.poll_interval)

    def _convert(self, job: Job) -> tuple[Path, dict[str, Any]]:
        """Run the pipeline on a job and return the file and the numbers."""
        options = job.options
        source = Path(str(options.get("source", job.source)))
        output = Path(str(options.get("output", source.with_suffix(".epub"))))
        work = self.work_dir / job.id

        language = options.get("language")
        config = self.config
        if isinstance(language, str) and language:
            config = with_language(self.config, language)

        pipeline = build_pipeline(config, source, work)
        pipeline.reporter = self._reporter(job.id)
        metadata = BookMetadata(
            title=str(options.get("title", source.stem)),
            author=str(options.get("author", "")),
            language=str(options.get("language", self.config.general.language)),
            year=options.get("year"),
        )
        result = pipeline.run(metadata, output)
        return output, _summary_of(result, source.stem)

    def _reporter(self, job_id: str) -> ProgressReporter:
        """Return the reporter that publishes the progress of a job."""

        def report(event: ProgressEvent) -> None:
            self.publish(
                WorkerEvent(
                    job_id=job_id,
                    stage=event.stage,
                    message=event.message,
                    page=event.page,
                    total=event.total,
                    percent=event.percent,
                )
            )

        return report


def status_counts(store: JobStore) -> dict[str, int]:
    """Return the number of jobs of every status."""
    return {status.value: store.count(status) for status in JobStatus}
