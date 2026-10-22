"""Tests for the page layout analysis.

The pages are synthetic: the text is drawn as rows of little blocks and the
illustrations as filled rectangles. That is enough to exercise the
projection profiles, the connected components and the footnote zone.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from scan2epub.domain.models import BlockKind, PageImage
from scan2epub.domain.ports import LayoutAnalyzer
from scan2epub.infrastructure.imaging.layout_analyzer import OpenCvLayoutAnalyzer

_PAGE_WIDTH = 900
_PAGE_HEIGHT = 1200
_BACKGROUND = 245
_INK = 30


def _empty_page() -> np.ndarray:
    """Return a page without any ink."""
    return np.full((_PAGE_HEIGHT, _PAGE_WIDTH), _BACKGROUND, dtype=np.uint8)


def _draw_line(image: np.ndarray, left: int, right: int, top: int, thickness: int = 16) -> None:
    """Draw a line of text as a row of words."""
    x = left
    while x < right:
        word = min(40, right - x)
        cv2.rectangle(image, (x, top), (x + word, top + thickness), _INK, -1)
        x += word + 12


def _draw_text(
    image: np.ndarray,
    left: int,
    right: int,
    top: int,
    count: int,
    step: int = 45,
    thickness: int = 16,
) -> None:
    """Draw several lines of text."""
    for index in range(count):
        _draw_line(image, left, right, top + index * step, thickness)


def _write(path: Path, image: np.ndarray) -> Path:
    """Write a page to disk and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)
    return path


def _page(path: Path, index: int = 0) -> PageImage:
    """Return the descriptor of a page on disk."""
    return PageImage(
        index=index,
        path=path,
        width=_PAGE_WIDTH,
        height=_PAGE_HEIGHT,
    )


def _single_column(tmp_path: Path) -> PageImage:
    """Return a page with a single column of text."""
    image = _empty_page()
    _draw_text(image, 60, 840, 120, 18)
    return _page(_write(tmp_path / "single.png", image))


def _two_columns(tmp_path: Path) -> PageImage:
    """Return a page with two columns of text."""
    image = _empty_page()
    _draw_text(image, 60, 380, 120, 18)
    _draw_text(image, 520, 840, 120, 18)
    return _page(_write(tmp_path / "two.png", image))


def _with_figure(tmp_path: Path) -> PageImage:
    """Return a page with a filled rectangle among the text."""
    image = _empty_page()
    _draw_text(image, 60, 840, 120, 6)
    cv2.rectangle(image, (350, 500), (550, 660), _INK, -1)
    _draw_text(image, 60, 840, 800, 3)
    return _page(_write(tmp_path / "figure.png", image))


def _with_footnote(tmp_path: Path) -> PageImage:
    """Return a page with a footnote separated from the body by a rule."""
    image = _empty_page()
    _draw_text(image, 60, 840, 120, 18)
    cv2.rectangle(image, (60, 960), (840, 962), _INK, -1)
    _draw_text(image, 60, 700, 1000, 2, step=40, thickness=10)
    return _page(_write(tmp_path / "footnote.png", image))


def test_the_analyser_satisfies_the_port() -> None:
    """The analyser implements the layout port of the domain."""
    assert isinstance(OpenCvLayoutAnalyzer(), LayoutAnalyzer)


def test_a_single_column_page_has_one_column(tmp_path: Path) -> None:
    """A page with one block of text has one column."""
    layout = OpenCvLayoutAnalyzer().analyze(_single_column(tmp_path))
    assert layout.columns == 1
    assert layout.blocks


def test_a_two_column_page_has_two_columns(tmp_path: Path) -> None:
    """A page with two blocks of text has two columns."""
    layout = OpenCvLayoutAnalyzer().analyze(_two_columns(tmp_path))
    assert layout.columns == 2


def test_the_blocks_belong_to_their_column(tmp_path: Path) -> None:
    """The blocks of a two column page know their column."""
    layout = OpenCvLayoutAnalyzer().analyze(_two_columns(tmp_path))
    assert {block.column for block in layout.blocks} == {0, 1}


def test_a_blank_page_has_no_block(tmp_path: Path) -> None:
    """A page without ink has an empty layout."""
    path = _write(tmp_path / "blank.png", _empty_page())
    layout = OpenCvLayoutAnalyzer().analyze(_page(path))
    assert layout.blocks == ()
    assert layout.columns == 1


def test_a_page_flagged_as_blank_is_not_read(tmp_path: Path) -> None:
    """A page that the source flagged as blank is not even read."""
    path = _write(tmp_path / "blank.png", _empty_page())
    image = PageImage(index=2, path=path, width=_PAGE_WIDTH, height=_PAGE_HEIGHT, is_blank=True)
    layout = OpenCvLayoutAnalyzer().analyze(image)
    assert layout.blocks == ()
    assert layout.columns == 1
    assert layout.index == 2


def test_a_filled_rectangle_is_an_illustration(tmp_path: Path) -> None:
    """A big blob of ink is an illustration and not a line of text."""
    layout = OpenCvLayoutAnalyzer().analyze(_with_figure(tmp_path))
    illustrations = [block for block in layout.blocks if block.kind is BlockKind.ILLUSTRATION]
    assert len(illustrations) == 1
    box = illustrations[0].bbox
    assert 0.3 < box.x0 < 0.45
    assert 0.35 < box.y0 < 0.5
    assert box.width > 0.15
    assert box.height > 0.1


def test_a_page_with_only_an_illustration_reports_it(tmp_path: Path) -> None:
    """A page that holds nothing but a picture still reports the picture."""
    image = _empty_page()
    cv2.rectangle(image, (350, 400), (550, 700), _INK, -1)
    layout = OpenCvLayoutAnalyzer().analyze(_page(_write(tmp_path / "only.png", image)))
    illustrations = [block for block in layout.blocks if block.kind is BlockKind.ILLUSTRATION]
    assert len(illustrations) == 1
    assert not [block for block in layout.blocks if block.kind is BlockKind.BODY]


def test_the_lines_of_text_are_body_blocks(tmp_path: Path) -> None:
    """The lines of the body are reported as body blocks."""
    layout = OpenCvLayoutAnalyzer().analyze(_single_column(tmp_path))
    body = [block for block in layout.blocks if block.kind is BlockKind.BODY]
    assert len(body) == 18


def test_the_blocks_are_in_reading_order(tmp_path: Path) -> None:
    """The blocks come from the top of the page to the bottom."""
    layout = OpenCvLayoutAnalyzer().analyze(_two_columns(tmp_path))
    keys = [(block.bbox.y0, block.bbox.x0) for block in layout.blocks]
    assert keys == sorted(keys)
    assert [block.order for block in layout.blocks] == list(range(len(layout.blocks)))


def test_the_footnote_zone_is_detected(tmp_path: Path) -> None:
    """The band of the footnotes is reported when a rule separates it."""
    layout = OpenCvLayoutAnalyzer().analyze(_with_footnote(tmp_path))
    notes = [block for block in layout.blocks if block.kind is BlockKind.FOOTNOTE]
    assert len(notes) == 1
    box = notes[0].bbox
    assert box.y0 > 0.8
    assert box.height > 0.02


def test_the_footnote_is_not_a_body_block(tmp_path: Path) -> None:
    """The lines of the footnotes are not reported as body text."""
    layout = OpenCvLayoutAnalyzer().analyze(_with_footnote(tmp_path))
    body = [block for block in layout.blocks if block.kind is BlockKind.BODY]
    assert body
    assert all(block.bbox.y1 < 0.82 for block in body)


def test_a_page_without_footnotes_has_no_footnote(tmp_path: Path) -> None:
    """A page whose band is empty has no footnote zone."""
    layout = OpenCvLayoutAnalyzer().analyze(_single_column(tmp_path))
    assert not [block for block in layout.blocks if block.kind is BlockKind.FOOTNOTE]


def test_a_footnote_without_a_separation_is_ignored(tmp_path: Path) -> None:
    """The band of the footnotes needs a rule or a gap to be a footnote."""
    image = _empty_page()
    _draw_text(image, 60, 840, 120, 19)
    _draw_text(image, 60, 700, 985, 1, thickness=10)
    layout = OpenCvLayoutAnalyzer().analyze(_page(_write(tmp_path / "close.png", image)))
    assert not [block for block in layout.blocks if block.kind is BlockKind.FOOTNOTE]


def test_the_footnote_zone_is_found_after_a_gap(tmp_path: Path) -> None:
    """A clear gap separates the footnotes from the body as well."""
    image = _empty_page()
    _draw_text(image, 60, 840, 120, 18)
    _draw_text(image, 60, 700, 1000, 1, thickness=10)
    layout = OpenCvLayoutAnalyzer().analyze(_page(_write(tmp_path / "gap.png", image)))
    assert [block for block in layout.blocks if block.kind is BlockKind.FOOTNOTE]


def test_the_layout_keeps_the_index_of_the_page(tmp_path: Path) -> None:
    """The layout knows the page it describes."""
    path = _write(tmp_path / "single.png", _empty_page())
    layout = OpenCvLayoutAnalyzer().analyze(_page(path, index=7))
    assert layout.index == 7


def test_a_missing_page_is_reported(tmp_path: Path) -> None:
    """A page that cannot be read is an error."""
    image = PageImage(index=0, path=tmp_path / "missing.png", width=10, height=10)
    with pytest.raises(ValueError):
        OpenCvLayoutAnalyzer().analyze(image)
