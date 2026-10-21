"""Tests for the progress reporting."""

from __future__ import annotations

from scan2epub.application.progress import ProgressEvent


def test_a_page_event_knows_its_scope() -> None:
    """An event that refers to a page of a stage is page scoped."""
    event = ProgressEvent(stage="ocr", page=3, total=10, percent=30.0)
    assert event.is_page_scoped
    assert event.page == 3
    assert event.total == 10


def test_a_stage_event_is_not_page_scoped() -> None:
    """An event about a whole stage has no page."""
    event = ProgressEvent(stage="epub", message="Writing")
    assert not event.is_page_scoped
    assert event.message == "Writing"
    assert event.percent == 0.0
