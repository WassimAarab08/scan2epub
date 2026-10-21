"""scan2epub — scanned public-domain books to clean, reflowable EPUB 3.

The package is organised as a light hexagonal architecture:

``domain``
    Pure data models and port (protocol) definitions. No I/O, no third-party
    framework imports.
``application``
    Pipeline stages, caching and job orchestration. Depends only on the ports.
``infrastructure``
    Adapters implementing the ports: OCR engines, text correctors, image
    processing, PDF rendering, EPUB writing and persistence.
``api``
    FastAPI application, job worker and Server-Sent Events.
``cli``
    Typer command line interface.
``eval``
    CER / WER metrics and the benchmark runner.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
