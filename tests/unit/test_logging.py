"""Tests for the secret redaction and the structured logging."""

from __future__ import annotations

import logging

from scan2epub.logging import configure_logging, get_logger, redact


def test_a_secret_in_a_string_is_masked() -> None:
    """A well-known credential shape never reaches the log."""
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in redact("key=sk-abcdefghijklmnopqrstuvwxyz")
    assert "ghp_abcdefghijklmnopqrstuvwxyz012345" not in redact(
        "token ghp_abcdefghijklmnopqrstuvwxyz012345"
    )


def test_a_sensitive_key_is_masked() -> None:
    """The value of a sensitive key is replaced."""
    assert redact("super-secret", "api_key") == "***REDACTED***"
    assert redact("super-secret", "OPENAI_API_KEY") == "***REDACTED***"
    assert redact("super-secret", "password") == "***REDACTED***"


def test_a_sensitive_key_is_masked_inside_a_mapping() -> None:
    """Nested mappings are walked."""
    payload = {"outer": {"api_key": "super-secret", "safe": "visible"}}
    result = redact(payload)
    assert result["outer"]["api_key"] == "***REDACTED***"
    assert result["outer"]["safe"] == "visible"


def test_lists_are_walked() -> None:
    """The values of a list are redacted too."""
    assert redact(["sk-abcdefghijklmnopqrstuvwxyz"]) == ["***REDACTED***"]


def test_other_values_are_untouched() -> None:
    """Ordinary data is not modified."""
    assert redact("hello") == "hello"
    assert redact(42) == 42
    assert redact(None) is None


def test_the_logger_can_be_configured() -> None:
    """The logging setup does not fail and the level is applied."""
    configure_logging(verbose=True)
    assert logging.getLogger().level == logging.DEBUG
    configure_logging(verbose=False)
    assert logging.getLogger().level == logging.INFO


def test_a_bound_logger_is_returned() -> None:
    """The helper returns a usable logger."""
    logger = get_logger("scan2epub.test")
    assert logger is not None
    logger.debug("hello", secret="sk-abcdefghijklmnopqrstuvwxyz")
