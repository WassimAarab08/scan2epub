"""Tests for the data model."""

from __future__ import annotations

from pathlib import Path

import pytest

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


def test_a_box_is_built_from_pixels() -> None:
    """The pixel coordinates are normalised."""
    box = BBox.from_pixels(100, 200, 400, 50, 1000, 2000)
    assert box.x0 == pytest.approx(0.1)
    assert box.y0 == pytest.approx(0.1)
    assert box.x1 == pytest.approx(0.5)
    assert box.y1 == pytest.approx(0.125)


def test_a_box_is_converted_back_to_pixels() -> None:
    """The round trip preserves the geometry."""
    box = BBox.from_pixels(100, 200, 400, 50, 1000, 2000)
    assert box.to_pixels(1000, 2000) == (100, 200, 400, 50)


def test_the_pixels_of_a_box_are_never_outside_the_page() -> None:
    """A box that goes past the edge is clamped."""
    box = BBox.from_pixels(-50, -50, 2000, 4000, 1000, 2000)
    assert box.x0 == 0.0
    assert box.y0 == 0.0
    assert box.x1 == 1.0
    assert box.y1 == 1.0


def test_a_malformed_box_is_rejected() -> None:
    """A box with negative extent is an error."""
    with pytest.raises(ValueError):
        BBox(0.5, 0.0, 0.1, 0.2)


def test_a_box_with_a_null_size_is_rejected() -> None:
    """A page of zero pixels cannot hold a box."""
    with pytest.raises(ValueError):
        BBox.from_pixels(0, 0, 10, 10, 0, 0)


def test_the_geometry_of_a_box() -> None:
    """The derived values are correct."""
    box = BBox(0.1, 0.2, 0.5, 0.6)
    assert box.width == pytest.approx(0.4)
    assert box.height == pytest.approx(0.4)
    assert box.area == pytest.approx(0.16)
    assert box.center_x == pytest.approx(0.3)
    assert box.center_y == pytest.approx(0.4)


def test_a_box_can_be_moved() -> None:
    """A box can be shifted vertically."""
    box = BBox(0.1, 0.2, 0.5, 0.3).shifted(0.1)
    assert box.y0 == pytest.approx(0.3)
    assert box.y1 == pytest.approx(0.4)


def test_a_block_keeps_its_lines() -> None:
    """The physical lines are preserved."""
    block = TextBlock.from_text("primera\nsegunda", BBox(0.1, 0.2, 0.9, 0.3))
    assert block.lines == ("primera", "segunda")
    assert block.text == "primera\nsegunda"
    assert block.char_count == len("primirasegunda")


def test_an_empty_block_is_detected() -> None:
    """A block without characters is empty."""
    assert TextBlock.from_text("   \n  ", BBox(0.1, 0.2, 0.9, 0.3)).is_empty
    assert not TextBlock.from_text("x", BBox(0.1, 0.2, 0.9, 0.3)).is_empty


def test_a_block_can_be_copied_with_a_new_role() -> None:
    """The copies are immutable."""
    block = TextBlock.from_text("texto", BBox(0.1, 0.2, 0.9, 0.3))
    heading = block.with_kind(BlockKind.HEADING)
    assert heading.kind is BlockKind.HEADING
    assert block.kind is BlockKind.BODY
    assert heading.with_level(2).level == 2
    assert heading.with_text("otro").text == "otro"


def test_a_page_image_reports_its_size() -> None:
    """The size of the page is available."""
    page = PageImage(index=0, path=Path("a.png"), width=100, height=200)
    assert page.size == (100, 200)
    assert not page.is_blank


def test_a_page_layout_holds_its_blocks() -> None:
    """The layout is a list of regions."""
    layout = PageLayout(
        index=0,
        blocks=(LayoutBlock(bbox=BBox(0.1, 0.2, 0.9, 0.3), kind=BlockKind.BODY),),
        columns=2,
    )
    assert len(layout.blocks) == 1
    assert layout.columns == 2


def test_a_book_is_built_from_its_parts() -> None:
    """The book gathers the chapters, the figures and the pages."""
    book = Book(
        metadata=BookMetadata(title="Libro", author="Anonimo", year="1765"),
        chapters=(Chapter(id="c1", title="Uno"),),
        figures=(Figure(id="f1", page=0, path=Path("f.png"), caption="Una figura"),),
        pages=(PageContent(index=0),),
    )
    assert book.metadata.title == "Libro"
    assert book.chapters[0].id == "c1"
    assert book.figures[0].caption == "Una figura"


def test_a_correction_result_carries_its_diffs() -> None:
    """The diffs of the corrector are preserved."""
    entry = DiffEntry(
        page=1,
        order=0,
        original="casa",
        corrected="cosa",
        distance=0.25,
        accepted=True,
    )
    result = CorrectionResult(entries=(entry,))
    assert result.entries[0].accepted
    assert result.entries[0].reason is None
