"""The SQLite queue of jobs.

The queue is a table of jobs. A worker claims a job with an **atomic**
update, so that two workers never take the same one:

```sql
UPDATE jobs SET status = 'running', started_at = ? WHERE id = ? AND status = 'queued'
```

The number of changed rows is the claim: one means the job is ours, zero
means that somebody else got there first.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

__all__ = ["Job", "JobStatus", "JobStore"]

#: The schema of the table of jobs.
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    source      TEXT NOT NULL,
    options     TEXT NOT NULL,
    output      TEXT,
    summary     TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at);
"""


class JobStatus(StrEnum):
    """The state of a job."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _empty_options() -> dict[str, Any]:
    """Return an empty table of options."""
    return {}


@dataclass(frozen=True, slots=True)
class Job:
    """A job of the queue."""

    id: str
    status: JobStatus
    source: str
    options: dict[str, Any] = field(default_factory=_empty_options)
    output: str | None = None
    summary: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None

    @property
    def is_finished(self) -> bool:
        """Whether the job will not change any more."""
        return self.status in {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED}


def _now() -> str:
    """Return the current time, in UTC, as an ISO string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class JobStore:
    """The queue of jobs, backed by SQLite."""

    def __init__(self, path: Path) -> None:
        """Initialise the store.

        Args:
            path: The file of the database. It is created when it does not
                exist.
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The connection is shared by the request handlers and by the worker
        # thread, so the check of the thread is disabled. SQLite serialises
        # the writes itself, and the transactions are short.
        self._connection = sqlite3.connect(
            str(self.path), isolation_level=None, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        # The write-ahead log lets the API read while the worker writes.
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Add the columns that a database of an older version does not have."""
        columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "summary" not in columns:
            self._connection.execute("ALTER TABLE jobs ADD COLUMN summary TEXT")

    def close(self) -> None:
        """Close the connection."""
        self._connection.close()

    def __enter__(self) -> JobStore:
        """Return the store, for the ``with`` statement."""
        return self

    def __exit__(self, *_args: object) -> None:
        """Close the store when the block ends."""
        self.close()

    def create(self, source: str, options: dict[str, Any] | None = None) -> Job:
        """Add a job to the queue.

        Args:
            source: The path of the PDF.
            options: The options of the conversion.

        Returns:
            The job that was created.
        """
        identifier = uuid.uuid4().hex
        now = _now()
        self._connection.execute(
            "INSERT INTO jobs (id, status, source, options, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                identifier,
                JobStatus.QUEUED.value,
                source,
                json.dumps(options or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        return Job(
            id=identifier,
            status=JobStatus.QUEUED,
            source=source,
            options=options or {},
            created_at=now,
            updated_at=now,
        )

    def get(self, identifier: str) -> Job | None:
        """Return a job, or ``None`` when it does not exist."""
        row = self._connection.execute("SELECT * FROM jobs WHERE id = ?", (identifier,)).fetchone()
        return _row_to_job(row) if row is not None else None

    def list(self, limit: int = 100) -> list[Job]:
        """Return the jobs, the newest first."""
        rows = self._connection.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_job(row) for row in rows]

    def update(
        self,
        identifier: str,
        *,
        source: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        """Change the source or the options of a job.

        The API uses it to move the uploaded PDF under the directory of the
        job, once the identifier of the job is known.

        Args:
            identifier: The identifier of the job.
            source: The new path of the PDF, when it changes.
            options: The new options of the conversion, when they change.
        """
        assignments: list[str] = []
        values: list[Any] = []
        if source is not None:
            assignments.append("source = ?")
            values.append(source)
        if options is not None:
            assignments.append("options = ?")
            values.append(json.dumps(options, ensure_ascii=False))
        if not assignments:
            return
        assignments.append("updated_at = ?")
        values.append(_now())
        values.append(identifier)
        self._connection.execute(
            f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?",  # noqa: S608 - fixed fragments
            values,
        )

    def claim(self) -> Job | None:
        """Claim the next queued job, atomically.

        Returns:
            The job, or ``None`` when the queue is empty.
        """
        row = self._connection.execute(
            "SELECT id FROM jobs WHERE status = ? ORDER BY created_at LIMIT 1",
            (JobStatus.QUEUED.value,),
        ).fetchone()
        if row is None:
            return None
        identifier = str(row["id"])
        now = _now()
        cursor = self._connection.execute(
            "UPDATE jobs SET status = ?, started_at = ?, updated_at = ? "
            "WHERE id = ? AND status = ?",
            (
                JobStatus.RUNNING.value,
                now,
                now,
                identifier,
                JobStatus.QUEUED.value,
            ),
        )
        if cursor.rowcount != 1:
            # Somebody else claimed it in the meantime.
            return None
        return self.get(identifier)

    def finish(
        self,
        identifier: str,
        output: str | None = None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        """Mark a job as done.

        Args:
            identifier: The identifier of the job.
            output: The path of the EPUB that was written.
            summary: The numbers of the conversion, for the interface.
        """
        now = _now()
        self._connection.execute(
            "UPDATE jobs SET status = ?, output = ?, summary = ?, finished_at = ?, "
            "updated_at = ? WHERE id = ?",
            (
                JobStatus.DONE.value,
                output,
                json.dumps(summary, ensure_ascii=False) if summary is not None else None,
                now,
                now,
                identifier,
            ),
        )

    def fail(self, identifier: str, error: str) -> None:
        """Mark a job as failed."""
        now = _now()
        self._connection.execute(
            "UPDATE jobs SET status = ?, error = ?, finished_at = ?, updated_at = ? WHERE id = ?",
            (JobStatus.FAILED.value, error, now, now, identifier),
        )

    def cancel(self, identifier: str) -> bool:
        """Cancel a job that has not started yet.

        Returns:
            Whether the job was cancelled.
        """
        now = _now()
        cursor = self._connection.execute(
            "UPDATE jobs SET status = ?, finished_at = ?, updated_at = ? "
            "WHERE id = ? AND status IN (?, ?)",
            (
                JobStatus.CANCELLED.value,
                now,
                now,
                identifier,
                JobStatus.QUEUED.value,
                JobStatus.RUNNING.value,
            ),
        )
        return cursor.rowcount == 1

    def requeue(self, identifier: str) -> bool:
        """Put a failed or cancelled job back in the queue.

        Returns:
            Whether the job was requeued.
        """
        now = _now()
        cursor = self._connection.execute(
            "UPDATE jobs SET status = ?, error = NULL, started_at = NULL, "
            "finished_at = NULL, updated_at = ? WHERE id = ?",
            (JobStatus.QUEUED.value, now, identifier),
        )
        return cursor.rowcount == 1

    def count(self, status: JobStatus | None = None) -> int:
        """Return the number of jobs, optionally of one status."""
        if status is None:
            row = self._connection.execute("SELECT COUNT(*) AS total FROM jobs").fetchone()
        else:
            row = self._connection.execute(
                "SELECT COUNT(*) AS total FROM jobs WHERE status = ?", (status.value,)
            ).fetchone()
        return int(row["total"]) if row is not None else 0


def _row_to_job(row: sqlite3.Row) -> Job:
    """Build a job from a row of the database."""
    options: dict[str, Any] = {}
    raw_options = row["options"]
    if isinstance(raw_options, str):
        try:
            parsed = json.loads(raw_options)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            parsed = {}
        if isinstance(parsed, dict):
            mapping = cast("dict[str, Any]", parsed)
            options = {str(key): value for key, value in mapping.items()}
    summary: dict[str, Any] | None = None
    raw_summary = row["summary"]
    if isinstance(raw_summary, str):
        try:
            parsed_summary = json.loads(raw_summary)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            parsed_summary = None
        if isinstance(parsed_summary, dict):
            mapping = cast("dict[str, Any]", parsed_summary)
            summary = {str(key): value for key, value in mapping.items()}
    return Job(
        id=str(row["id"]),
        status=JobStatus(str(row["status"])),
        source=str(row["source"]),
        options=options,
        output=row["output"],
        summary=summary,
        error=row["error"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )
