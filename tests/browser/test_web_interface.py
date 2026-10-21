"""Browser test of the web interface.

The API ships a small web page that converts a book. This test drives it with
a real browser: it uploads a PDF through the form, waits for the conversion
and checks the answer and the download.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser


def _free_port() -> int:
    """Return a port that is free right now."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Start the API on a free port and return its base URL."""
    import uvicorn

    import scan2epub.api.app as api_module
    from scan2epub.api.app import create_app
    from scan2epub.config import Config, GeneralConfig

    data_dir = tmp_path_factory.mktemp("web-data")
    original = api_module.DATA_DIR
    api_module.DATA_DIR = data_dir

    config = Config(general=GeneralConfig(language="eng", validate_epub=False))
    app = create_app(config)

    port = _free_port()
    server_config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    instance = uvicorn.Server(server_config)
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if instance.started:
            break
        time.sleep(0.1)
    else:  # pragma: no cover - the server always starts
        pytest.fail("The API did not start")

    try:
        yield base
    finally:
        instance.should_exit = True
        thread.join(timeout=10)
        api_module.DATA_DIR = original


def test_the_page_is_served(page_factory: object, server: str) -> None:
    """The landing page is served and looks like a converter."""
    page = page_factory()
    page.goto(server)  # type: ignore[attr-defined]
    page.wait_for_selector("h1")  # type: ignore[attr-defined]
    assert "scan2epub" in page.inner_text("h1")  # type: ignore[attr-defined]
    assert page.query_selector("#file") is not None  # type: ignore[attr-defined]
    assert page.query_selector("#submit") is not None  # type: ignore[attr-defined]


def test_the_health_check_answers_in_the_browser(page_factory: object, server: str) -> None:
    """The health check is reachable and reports the engines."""
    page = page_factory()
    response = page.goto(f"{server}/health")  # type: ignore[attr-defined]
    assert response is not None
    assert response.status == 200
    assert "tesseract" in page.inner_text("body")  # type: ignore[attr-defined]


def test_a_book_is_converted_through_the_form(
    page_factory: object, server: str, sample_pdf: Path
) -> None:
    """The whole journey works in a real browser."""
    page = page_factory()
    page.goto(server)  # type: ignore[attr-defined]
    page.wait_for_selector("#file")  # type: ignore[attr-defined]

    page.set_input_files("#file", str(sample_pdf))  # type: ignore[attr-defined]
    page.fill("#title", "El libro de prueba")  # type: ignore[attr-defined]
    page.fill("#author", "Anónimo")  # type: ignore[attr-defined]
    page.select_option("#lang", "eng")  # type: ignore[attr-defined]
    page.click("#submit")  # type: ignore[attr-defined]

    # The conversion takes a few seconds: wait for the answer.
    page.wait_for_selector("#result a", timeout=120_000)  # type: ignore[attr-defined]
    result = page.inner_text("#result")  # type: ignore[attr-defined]
    assert "El libro de prueba" in result
    assert "3 pages" in result

    # The download link really serves an EPUB.
    href = page.get_attribute("#result a", "href")  # type: ignore[attr-defined]
    assert href
    response = page.request.get(f"{server}{href}")  # type: ignore[attr-defined]
    assert response.status == 200
    assert response.body()[:2] == b"PK"
