"""Core data model of the scan2epub pipeline.

These are pure, immutable data containers. The pipeline stages exchange them;
the infrastructure adapters produce and consume them. Coordinates are always
**normalised** to the ``0.0 .. 1.0`` range relative to the page size so that
they survive rescaling and can be compared across engines.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path

__all__ = [
    "BBox",
    "BlockKind",
    "Book",
    "BookMetadata",
    "Chapter",
    "CorrectionResult",
    "DiffEntry",
    "Figure",
    "LayoutBlock",
    "PageContent",
    "PageImage",
    "PageLayout",
    "TextBlock",
]


class BlockKind(StrEnum):
    """Semantic role of a block of text on a page."""

    BODY = "body"
    HEADING = "heading"
    FOOTNOTE = "footnote"
    CAPTION = "caption"
    ILLUSTRATION = "illustration"
    RUNNING_HEAD = "running_head"
    PAGE_NUMBER = "page_number"


@dataclass(frozen=True, slots=True)
class BBox:
    """An axis-aligned bounding box with normalised coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        """Reject a malformed bounding box."""
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError(f"Invalid bounding box: {self!r}")

    @classmethod
    def from_pixels(
        cls, left: int, top: int, width: int, height: int, page_width: int, page_height: int
    ) -> BBox:
        """Build a box from pixel coordinates, normalising them to ``0..1``."""
        if page_width <= 0 or page_height <= 0:
            raise ValueError("Page dimensions must be positive")
        x0 = max(0.0, min(1.0, left / page_width))
        y0 = max(0.0, min(1.0, top / page_height))
        x1 = max(0.0, min(1.0, (left + width) / page_width))
        y1 = max(0.0, min(1.0, (top + height) / page_height))
        return cls(x0, y0, x1, y1)

    @property
    def width(self) -> float:
        """Horizontal extent of the box."""
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        """Vertical extent of the box."""
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        """Area of the box in normalised units."""
        return self.width * self.height

    @property
    def center_x(self) -> float:
        """Horizontal centre of the box."""
        return (self.x0 + self.x1) / 2.0

    @property
    def center_y(self) -> float:
        """Vertical centre of the box."""
        return (self.y0 + self.y1) / 2.0

    def to_pixels(self, page_width: int, page_height: int) -> tuple[int, int, int, int]:
        """Convert back to ``(left, top, width, height)`` in pixels."""
        left = round(self.x0 * page_width)
        top = round(self.y0 * page_height)
        width = max(0, round(self.width * page_width))
        height = max(0, round(self.height * page_height))
        return left, top, width, height

    def shifted(self, dy: float) -> BBox:
        """Return a copy moved vertically by ``dy`` (normalised units)."""
        return BBox(self.x0, self.y0 + dy, self.x1, self.y1 + dy)


@dataclass(frozen=True, slots=True)
class TextBlock:
    """A logical block of text, made of one or more physical lines.

    Keeping the physical lines is essential: end-of-line hyphenation can only
    be repaired while the line breaks are still known.
    """

    lines: tuple[str, ...]
    bbox: BBox
    confidence: float = 1.0
    kind: BlockKind = BlockKind.BODY
    order: int = 0
    page: int = 0
    column: int = 0
    level: int = 0

    @classmethod
    def from_text(
        cls,
        text: str,
        bbox: BBox,
        *,
        confidence: float = 1.0,
        kind: BlockKind = BlockKind.BODY,
        order: int = 0,
        page: int = 0,
        column: int = 0,
        level: int = 0,
    ) -> TextBlock:
        """Build a block from a plain string, splitting it on newlines."""
        return cls(
            lines=tuple(text.split("\n")),
            bbox=bbox,
            confidence=confidence,
            kind=kind,
            order=order,
            page=page,
            column=column,
            level=level,
        )

    @property
    def text(self) -> str:
        """The block text with the physical line breaks preserved."""
        return "\n".join(self.lines)

    @property
    def is_empty(self) -> bool:
        """Whether the block carries no visible characters."""
        return not self.text.strip()

    @property
    def char_count(self) -> int:
        """Number of non-whitespace characters."""
        return len("".join(self.text.split()))

    def with_kind(self, kind: BlockKind) -> TextBlock:
        """Return a copy with a different semantic role."""
        return replace(self, kind=kind)

    def with_level(self, level: int) -> TextBlock:
        """Return a copy with a different heading level."""
        return replace(self, level=level)

    def with_lines(self, lines: tuple[str, ...]) -> TextBlock:
        """Return a copy with different physical lines."""
        return replace(self, lines=lines)

    def with_text(self, text: str) -> TextBlock:
        """Return a copy whose content is ``text`` (split on newlines)."""
        return replace(self, lines=tuple(text.split("\n")))


@dataclass(frozen=True, slots=True)
class PageImage:
    """A rasterised page of the source document."""

    index: int
    path: Path
    width: int
    height: int
    is_blank: bool = False

    @property
    def size(self) -> tuple[int, int]:
        """``(width, height)`` in pixels."""
        return self.width, self.height


@dataclass(frozen=True, slots=True)
class LayoutBlock:
    """A region of a page identified by the layout analyser."""

    bbox: BBox
    kind: BlockKind = BlockKind.BODY
    column: int = 0
    order: int = 0


@dataclass(frozen=True, slots=True)
class PageLayout:
    """The structural analysis of a single page."""

    index: int
    blocks: tuple[LayoutBlock, ...] = ()
    columns: int = 1


@dataclass(frozen=True, slots=True)
class PageContent:
    """The recognised and cleaned text of a single page."""

    index: int
    blocks: tuple[TextBlock, ...] = ()


@dataclass(frozen=True, slots=True)
class Chapter:
    """A logical division of the book that becomes one EPUB content document."""

    id: str
    title: str
    level: int = 1
    start_page: int = 0
    end_page: int = 0
    blocks: tuple[TextBlock, ...] = ()


@dataclass(frozen=True, slots=True)
class Figure:
    """An illustration extracted from a page."""

    id: str
    page: int
    path: Path
    caption: str | None = None


@dataclass(frozen=True, slots=True)
class BookMetadata:
    """Descriptive metadata of the generated EPUB.

    All fields except the title are optional and can be filled in by the user
    after the conversion.
    """

    title: str
    author: str = ""
    language: str = "es"
    year: str | None = None
    publisher: str | None = None
    identifier: str = ""
    description: str | None = None
    subject: str | None = None


@dataclass(frozen=True, slots=True)
class Book:
    """The fully structured book, ready to be written as an EPUB."""

    metadata: BookMetadata
    chapters: tuple[Chapter, ...] = ()
    figures: tuple[Figure, ...] = ()
    pages: tuple[PageContent, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DiffEntry:
    """The record of a single correction proposed by a text corrector."""

    page: int
    order: int
    original: str
    corrected: str
    distance: float
    accepted: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    """The outcome of a text-correction pass."""

    blocks: tuple[TextBlock, ...] = ()
    entries: tuple[DiffEntry, ...] = ()
