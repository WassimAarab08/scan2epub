"""Structured logging with automatic secret redaction.

Every log record passes through a redactor that removes anything that looks
like a credential. The redactor works on the *rendered* event, so it also
catches secrets that are embedded in exception messages or in third-party
payloads.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import MutableMapping
from typing import Any, cast

import structlog

__all__ = ["configure_logging", "get_logger", "redact"]

#: Patterns that are replaced by a placeholder in any logged text.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
    re.compile(r"\bey[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
)

#: Configuration keys whose value is always masked, whatever it looks like.
_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "token",
        "access_token",
        "secret",
        "password",
        "passwd",
        "x-api-key",
        "openai_api_key",
        "anthropic_api_key",
        "gemini_api_key",
    }
)

_REDACTED = "***REDACTED***"


def _mask_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return lowered in _SECRET_KEYS or lowered.endswith(("_key", "_token", "_secret", "_password"))


def redact(value: object, key: str | None = None) -> object:
    """Return ``value`` with any credential removed.

    Strings are scanned for well-known credential shapes; mappings are walked
    recursively and the values of sensitive keys are masked.
    """
    if key is not None and _mask_key(key) and value is not None:
        return _REDACTED
    if isinstance(value, str):
        redacted = value
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(_REDACTED, redacted)
        return redacted
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        return {str(name): redact(item, str(name)) for name, item in mapping.items()}
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [redact(item) for item in items]
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        return tuple(redact(item) for item in items)
    return value


class _CurrentStderr:
    """A stream that always writes to the *current* ``sys.stderr``.

    The standard streams are replaced by the test runners, and the ones they
    replace are closed when the test ends. A logger that kept a reference to
    the stream of the moment it was configured would fail with *"I/O
    operation on closed file"* as soon as something was logged afterwards.
    """

    def write(self, data: str) -> int:
        """Write the data to the current standard error."""
        return sys.stderr.write(data)

    def flush(self) -> None:
        """Flush the current standard error."""
        sys.stderr.flush()

    def isatty(self) -> bool:
        """Return whether the current standard error is a terminal."""
        return bool(getattr(sys.stderr, "isatty", lambda: False)())


#: The stream that the logger writes to.
STDERR = _CurrentStderr()


def _redact_processor(
    _logger: Any,  # noqa: ANN401 - the structlog processor signature is fixed
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Redact the whole event dictionary."""
    return {str(name): redact(item, str(name)) for name, item in event_dict.items()}


def configure_logging(*, verbose: bool = False, json_logs: bool = False) -> None:
    """Configure the root logger and structlog.

    Args:
        verbose: Emit ``DEBUG`` records instead of ``INFO``.
        json_logs: Emit machine-readable JSON lines instead of a console
            renderer.
    """
    level = logging.DEBUG if verbose else logging.INFO
    level_name = os.environ.get("SCAN2EPUB_LOG_LEVEL", "").upper()
    if level_name in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = getattr(logging, level_name)

    logging.basicConfig(
        format="%(message)s",
        stream=STDERR,
        level=level,
    )
    # ``basicConfig`` does nothing when the root logger already has handlers,
    # which is the case when the command is imported by a test runner or by a
    # server that configured logging itself. The requested level is applied
    # in any case, so ``--verbose`` is never silently ignored.
    logging.getLogger().setLevel(level)
    # structlog must not route through stdlib logging twice.
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            (
                structlog.processors.JSONRenderer()
                if json_logs
                else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=cast("Any", STDERR)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
