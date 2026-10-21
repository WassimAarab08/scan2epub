"""Application layer: pipeline stages, caching and job orchestration.

The stages in this package are deliberately free of framework imports. They
depend on the ports declared in :mod:`scan2epub.domain.ports` and on the pure
helpers of :mod:`scan2epub.domain`.
"""

from __future__ import annotations

from scan2epub.application.progress import ProgressEvent, ProgressReporter
from scan2epub.application.stages.clean import CleanResult, clean_pages
from scan2epub.application.stages.structure import structure_book

__all__ = [
    "CleanResult",
    "ProgressEvent",
    "ProgressReporter",
    "clean_pages",
    "structure_book",
]
