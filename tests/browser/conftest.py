"""Fixtures shared by the browser tests.

There is a single Playwright instance for the whole session: two concurrent
`sync_playwright()` contexts in the same thread do not work.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

playwright_api = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed.")


@pytest.fixture(scope="session")
def browser() -> Iterator[object]:
    """Return a Chromium browser, or skip the test when it is missing."""
    with playwright_api.sync_playwright() as playwright:
        try:
            instance = playwright.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on the machine
            pytest.skip(f"Chromium is not available: {exc}")
        yield instance
        instance.close()


@pytest.fixture(scope="session")
def page_factory(browser: object) -> Iterator[object]:
    """Return a factory that opens a new page."""
    contexts: list[object] = []

    def factory(**kwargs: object) -> object:
        context = browser.new_context(**kwargs)  # type: ignore[attr-defined]
        contexts.append(context)
        return context.new_page()

    yield factory
    for context in contexts:
        context.close()  # type: ignore[attr-defined]
