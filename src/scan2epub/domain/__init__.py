"""Domain layer: pure data models shared by every pipeline stage.

Nothing in this package may perform I/O or import a web framework. The models
below are the only vocabulary shared between the application layer and the
infrastructure adapters.
"""

from __future__ import annotations

from scan2epub.domain.models import (
    BBox,
    BlockKind,
    Book,
    BookMetadata,
    Chapter,
    CorrectionResult,
    DiffEntry,
    Figure,
    LayoutBlock,
    PageContent,
    PageImage,
    PageLayout,
    TextBlock,
)
from scan2epub.domain.ports import (
    Cache,
    LayoutAnalyzer,
    OcrEngine,
    PagePreprocessor,
    PageSource,
    TextCorrector,
)

__all__ = [
    "BBox",
    "BlockKind",
    "Book",
    "BookMetadata",
    "Cache",
    "Chapter",
    "CorrectionResult",
    "DiffEntry",
    "Figure",
    "LayoutAnalyzer",
    "LayoutBlock",
    "OcrEngine",
    "PageContent",
    "PageImage",
    "PageLayout",
    "PagePreprocessor",
    "PageSource",
    "TextBlock",
    "TextCorrector",
]
