"""The ``scan2epub serve`` command.

It starts the REST API, which exposes the same pipeline as the command
line. The service listens on ``127.0.0.1`` by default: put it behind a
reverse proxy with TLS and authentication before exposing it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

__all__ = ["serve"]


def serve(
    host: Annotated[
        str, typer.Option("--host", help="The address the service listens on.")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535, help="The port.")] = 8000,
    reload: Annotated[
        bool, typer.Option("--reload", help="Reload the code on every change.")
    ] = False,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Where the uploads and the results are written."),
    ] = None,
) -> None:
    """Start the REST API."""
    import os  # noqa: PLC0415 - the import is cheap but uvicorn is not

    import uvicorn  # noqa: PLC0415 - uvicorn is an optional dependency

    from scan2epub.logging import get_logger  # noqa: PLC0415

    logger = get_logger(__name__)
    if data_dir is not None:
        os.environ["SCAN2EPUB_DATA_DIR"] = str(data_dir)

    logger.info("api.starting", host=host, port=port)
    uvicorn.run(
        "scan2epub.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
