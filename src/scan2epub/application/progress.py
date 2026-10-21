"""Progress reporting primitives shared by the CLI, the worker and the API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

__all__ = ["ProgressEvent", "ProgressReporter"]


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """A single progress notification emitted by the pipeline."""

    stage: str
    message: str = ""
    page: int | None = None
    total: int | None = None
    percent: float = 0.0

    @property
    def is_page_scoped(self) -> bool:
        """Whether the event refers to a specific page of a multi-page stage."""
        return self.page is not None and self.total is not None


class ProgressReporter(Protocol):
    """Anything that can consume pipeline progress events."""

    def __call__(self, event: ProgressEvent) -> None:
        """Handle a progress event."""
        ...
