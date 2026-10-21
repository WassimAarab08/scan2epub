"""Exception hierarchy for scan2epub.

Every error raised by the library derives from :class:`Scan2EpubError` so that
the CLI and the API can turn failures into actionable user-facing messages
instead of raw tracebacks.
"""

from __future__ import annotations

__all__ = [
    "BudgetExceededError",
    "ConfigurationError",
    "EngineNotAvailableError",
    "EpubValidationError",
    "OcrError",
    "PipelineError",
    "Scan2EpubError",
]


class Scan2EpubError(Exception):
    """Base class for every error raised by scan2epub."""


class ConfigurationError(Scan2EpubError):
    """The user configuration is invalid or incomplete."""


class EngineNotAvailableError(Scan2EpubError):
    """A requested OCR engine or text corrector is not installed or not registered."""


class OcrError(Scan2EpubError):
    """An OCR engine failed while recognising a page."""


class PipelineError(Scan2EpubError):
    """A pipeline stage failed."""


class BudgetExceededError(Scan2EpubError):
    """The estimated or actual cost exceeded the configured budget."""


class EpubValidationError(Scan2EpubError):
    """The generated EPUB did not pass EPUBCheck."""
