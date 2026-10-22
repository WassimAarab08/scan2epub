"""Page layout analysis with OpenCV.

The layout of a printed page is a geometrical fact: the ink sits in columns,
the illustrations are big blobs and the footnotes live in a band at the
bottom, separated from the body by a rule or by a clear gap. This module
reads those facts from the pixels with the projection profiles and the
connected components, without any model and without any tuning per book.

Everything the analyser returns is expressed in the normalised coordinates of
the page, exactly like the rest of the project.
"""

from __future__ import annotations

import itertools

import cv2
import numpy as np
from cv2.typing import MatLike
from numpy.typing import NDArray

from scan2epub.domain.models import BBox, BlockKind, LayoutBlock, PageImage, PageLayout

__all__ = ["OpenCvLayoutAnalyzer"]

#: A column is empty when it holds at most this fraction of the page height.
_EMPTY_COLUMN_TOLERANCE = 0.005

#: A figure is much larger than a line of text when it is at least this
#: many times taller than the lines of the page.
_FIGURE_HEIGHT_FACTOR = 3.0

#: The smallest height of a figure, as a fraction of the page height.
_FIGURE_MIN_HEIGHT = 0.025

#: A line of text is never this tall, as a fraction of the page height. A
#: taller band means that the page holds no text at all.
_MAX_TEXT_HEIGHT = 0.1

#: A horizontal rule is at most this thick, as a fraction of the page height.
_RULE_MAX_THICKNESS = 0.005

#: A rule is at least this wide, as a fraction of the page width.
_RULE_MIN_WIDTH = 0.4

#: A line of the footnote zone is at least this wide, as a fraction of the
#: page width. A folio is narrower than that.
_FOOTNOTE_MIN_WIDTH = 0.08

#: The smallest gap that separates the body from the footnotes, as a
#: fraction of the page height.
_FOOTNOTE_MIN_GAP = 0.012

#: The gap that separates the body from the footnotes is this many times
#: the leading of the body.
_FOOTNOTE_GAP_FACTOR = 1.2


def _runs(mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """Return the ``(start, end)`` bounds of the runs of ``True`` in ``mask``.

    Args:
        mask: A one-dimensional boolean array.

    Returns:
        One ``(start, end)`` pair per run of consecutive ``True`` values. The
        end is exclusive. The list is empty when the mask holds no ``True``.
    """
    indices = np.flatnonzero(mask)
    if indices.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(indices) > 1)
    starts = np.concatenate((indices[:1], indices[breaks + 1]))
    ends = np.concatenate((indices[breaks], indices[-1:]))
    return [(int(start), int(end) + 1) for start, end in zip(starts, ends, strict=True)]


class OpenCvLayoutAnalyzer:
    """Find the columns, the figures and the footnote zone of a page.

    Attributes:
        min_gap: The smallest width of the gutter that separates two columns,
            as a fraction of the page width.
        min_figure_area: The smallest area of an illustration, as a fraction
            of the area of the page.
        footnote_zone: The height at which the footnote zone starts, as a
            fraction of the page height.
    """

    def __init__(
        self,
        *,
        min_gap: float = 0.03,
        min_figure_area: float = 0.02,
        footnote_zone: float = 0.82,
    ) -> None:
        """Initialise the analyser.

        Args:
            min_gap: The smallest width of the gutter that separates two
                columns, as a fraction of the page width.
            min_figure_area: The smallest area of an illustration, as a
                fraction of the area of the page.
            footnote_zone: The height at which the footnote zone starts, as a
                fraction of the page height.
        """
        self.min_gap = min_gap
        self.min_figure_area = min_figure_area
        self.footnote_zone = footnote_zone

    def analyze(self, image: PageImage) -> PageLayout:
        """Return the layout of ``image``.

        The blocks are returned in reading order: from the top of the page to
        the bottom, and from the left to the right inside a line. Every block
        knows the column it belongs to, so a consumer that reads a page
        column by column can regroup them.

        Args:
            image: The page to analyse.

        Returns:
            The blocks of the page, the number of columns and the index of the
            page. A blank page returns an empty layout with a single column.

        Raises:
            ValueError: If the page image cannot be read.
        """
        if image.is_blank:
            return PageLayout(index=image.index)
        gray = cv2.imread(str(image.path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            raise ValueError(f"Cannot read page image: {image.path}")
        height, width = gray.shape[:2]
        ink = self._ink(gray)
        if not bool(ink.any()):
            return PageLayout(index=image.index)

        columns = self._columns(ink, width)
        figures = self._figures(ink, width, height)
        blocks: list[LayoutBlock] = []
        for left, top, right, bottom in figures:
            blocks.append(
                LayoutBlock(
                    bbox=BBox.from_pixels(left, top, right - left, bottom - top, width, height),
                    kind=BlockKind.ILLUSTRATION,
                    column=self._column_of(columns, (left + right) / 2.0),
                )
            )
        footnote, band_top = self._footnote(ink, columns, figures, width, height)
        if footnote is not None:
            blocks.append(footnote)
        blocks.extend(self._text_blocks(ink, columns, figures, width, height, band_top))

        blocks.sort(key=lambda block: (block.bbox.y0, block.bbox.x0))
        ordered = tuple(
            LayoutBlock(bbox=block.bbox, kind=block.kind, column=block.column, order=order)
            for order, block in enumerate(blocks)
        )
        return PageLayout(index=image.index, blocks=ordered, columns=len(columns))

    def _ink(self, gray: MatLike) -> NDArray[np.bool_]:
        """Return the mask of the ink of a page.

        Args:
            gray: The grayscale page.

        Returns:
            A boolean array that is ``True`` where the page carries ink.
        """
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        return np.asarray(binary) > 0

    def _columns(self, ink: NDArray[np.bool_], width: int) -> list[tuple[int, int]]:
        """Return the horizontal bounds of every column of the page.

        The columns are the valleys of the vertical projection profile of the
        ink: the bands of columns that hold no ink at all. Only the valleys
        that are wide enough to separate two columns are kept.

        Args:
            ink: The mask of the ink of the page.
            width: The width of the page in pixels.

        Returns:
            One ``(left, right)`` pair per column. The list is empty when the
            page holds no ink.
        """
        profile = ink.sum(axis=0)
        tolerance = max(1, round(_EMPTY_COLUMN_TOLERANCE * ink.shape[0]))
        inked = _runs(profile > tolerance)
        if not inked:
            return []
        min_gap = max(1, round(self.min_gap * width))
        limits: list[tuple[int, int]] = []
        start = inked[0][0]
        for (_, previous_end), (next_start, _) in itertools.pairwise(inked):
            if next_start - previous_end < min_gap:
                continue
            limits.append((start, previous_end))
            start = next_start
        limits.append((start, inked[-1][1]))
        return limits

    def _column_of(self, columns: list[tuple[int, int]], x: float) -> int:
        """Return the index of the column that holds the position ``x``."""
        for index, (left, right) in enumerate(columns):
            if left <= x < right:
                return index
        return len(columns) - 1 if columns else 0

    def _figures(
        self, ink: NDArray[np.bool_], width: int, height: int
    ) -> list[tuple[int, int, int, int]]:
        """Return the bounding boxes of the illustrations of the page.

        An illustration is a connected component of ink that is much larger
        than a line of text and that is not made of horizontal strokes alone.

        Args:
            ink: The mask of the ink of the page.
            width: The width of the page in pixels.
            height: The height of the page in pixels.

        Returns:
            One ``(left, top, right, bottom)`` box per illustration.
        """
        mask = np.asarray(ink, dtype=np.uint8)
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        table = np.asarray(stats)
        line_height = self._line_height(ink)
        if line_height > _MAX_TEXT_HEIGHT * height:
            # The page holds no text: every big blob is an illustration.
            line_height = 0.0
        min_height = max(_FIGURE_HEIGHT_FACTOR * line_height, _FIGURE_MIN_HEIGHT * height)
        min_area = self.min_figure_area * width * height
        figures: list[tuple[int, int, int, int]] = []
        for index in range(1, count):
            left, top, box_width, box_height = (int(value) for value in table[index][:4])
            if box_width * box_height < min_area:
                continue
            if box_height < min_height:
                continue
            if not self._covers_its_rows(ink, left, top, box_width, box_height):
                continue
            figures.append((left, top, left + box_width, top + box_height))
        return figures

    def _line_height(self, ink: NDArray[np.bool_]) -> float:
        """Return the height of a line of text of the page, in pixels.

        The lines are the bands of the horizontal projection profile of the
        ink. The median of their heights is robust against the figures and
        the rules, which are much taller than a line.

        Args:
            ink: The mask of the ink of the page.

        Returns:
            The height of a line of text. Zero when the page holds no text.
        """
        profile = ink.sum(axis=1)
        heights = [end - start for start, end in _runs(profile > 0)]
        return self._median(heights)

    def _covers_its_rows(
        self, ink: NDArray[np.bool_], left: int, top: int, width: int, height: int
    ) -> bool:
        """Whether a box holds strokes that are not horizontal lines.

        A component made of horizontal strokes alone leaves blank rows
        between them. An illustration, even a solid one, spreads its ink
        over the whole height of its box.

        Args:
            ink: The mask of the ink of the page.
            left: The left edge of the box.
            top: The top edge of the box.
            width: The width of the box.
            height: The height of the box.

        Returns:
            ``True`` when the ink covers enough rows of the box.
        """
        if height <= 0 or width <= 0:
            return False
        window = ink[top : top + height, left : left + width]
        covered = int((window.sum(axis=1) > 0).sum())
        return covered >= height / 2.0

    def _text_blocks(
        self,
        ink: NDArray[np.bool_],
        columns: list[tuple[int, int]],
        figures: list[tuple[int, int, int, int]],
        width: int,
        height: int,
        band_top: int,
    ) -> list[LayoutBlock]:
        """Return the lines of text of the page, one block per line.

        Args:
            ink: The mask of the ink of the page.
            columns: The horizontal bounds of every column.
            figures: The bounding boxes of the illustrations, which are left
                out of the text.
            width: The width of the page in pixels.
            height: The height of the page in pixels.
            band_top: The first row of the footnote zone, which is left out of
                the text of the body.

        Returns:
            One block per line of text.
        """
        blocks: list[LayoutBlock] = []
        for index, (left, right) in enumerate(columns):
            window = ink[:band_top, left:right].copy()
            for figure_left, figure_top, figure_right, figure_bottom in figures:
                if figure_right <= left or figure_left >= right:
                    continue
                rows = slice(max(0, figure_top - 1), min(band_top, figure_bottom + 1))
                cells = slice(
                    max(0, figure_left - left - 1),
                    max(0, min(right - left, figure_right - left + 1)),
                )
                window[rows, cells] = False
            profile = window.sum(axis=1)
            for top, bottom in _runs(profile > 0):
                band = window[top:bottom]
                inked = np.flatnonzero(band.any(axis=0))
                if inked.size == 0:
                    continue
                band_left = left + int(inked[0])
                band_right = left + int(inked[-1]) + 1
                if self._is_rule((top, bottom, band_left, band_right), width, height):
                    # A rule separates the text, it is not text.
                    continue
                blocks.append(
                    LayoutBlock(
                        bbox=BBox.from_pixels(
                            band_left, top, band_right - band_left, bottom - top, width, height
                        ),
                        kind=BlockKind.BODY,
                        column=index,
                    )
                )
        return blocks

    def _footnote(
        self,
        ink: NDArray[np.bool_],
        columns: list[tuple[int, int]],
        figures: list[tuple[int, int, int, int]],
        width: int,
        height: int,
    ) -> tuple[LayoutBlock | None, int]:
        """Return the footnote zone of the page, when there is one.

        The footnote zone is the band at the bottom of the page where the
        smaller type lives. It is only reported when the band holds some
        text and when that text is separated from the body of the page,
        either by a rule or by a clear gap.

        Args:
            ink: The mask of the ink of the page.
            columns: The horizontal bounds of every column.
            figures: The bounding boxes of the illustrations, which are not
                footnotes.
            width: The width of the page in pixels.
            height: The height of the page in pixels.

        Returns:
            The block of the footnote zone, or ``None`` when the page has no
            footnote, together with the first row of the band.
        """
        band_top = min(height, max(0, round(self.footnote_zone * height)))
        if band_top >= height:
            return None, height
        band = ink[band_top:].copy()
        for figure_left, figure_top, figure_right, figure_bottom in figures:
            if figure_bottom <= band_top:
                continue
            rows = slice(max(0, figure_top - band_top - 1), figure_bottom - band_top + 1)
            cells = slice(max(0, figure_left - 1), figure_right + 1)
            band[rows, cells] = False
        content = self._band_lines(band, band_top, width)
        if not content:
            return None, height
        text_lines = [line for line in content if not self._is_rule(line, width, height)]
        if not text_lines:
            return None, height
        first_top = min(line[0] for line in text_lines)
        if not self._is_separated(ink, first_top, width, height):
            return None, height
        left = min(line[2] for line in text_lines)
        right = max(line[3] for line in text_lines)
        top = min(line[0] for line in text_lines)
        bottom = max(line[1] for line in text_lines)
        footnote = LayoutBlock(
            bbox=BBox.from_pixels(left, top, right - left, bottom - top, width, height),
            kind=BlockKind.FOOTNOTE,
            column=self._column_of(columns, (left + right) / 2.0),
        )
        return footnote, band_top

    def _band_lines(
        self, band: NDArray[np.bool_], offset: int, width: int
    ) -> list[tuple[int, int, int, int]]:
        """Return the lines of ink of a band of the page.

        Args:
            band: The mask of the ink of the band.
            offset: The row of the page where the band starts.
            width: The width of the page in pixels.

        Returns:
            One ``(top, bottom, left, right)`` box per line of the band.
        """
        profile = band.sum(axis=1)
        lines: list[tuple[int, int, int, int]] = []
        for top, bottom in _runs(profile > 0):
            inked = np.flatnonzero(band[top:bottom].any(axis=0))
            if inked.size == 0:
                continue
            left = int(inked[0])
            right = int(inked[-1]) + 1
            if right - left < _FOOTNOTE_MIN_WIDTH * width:
                continue
            lines.append((offset + top, offset + bottom, left, right))
        return lines

    def _is_rule(self, line: tuple[int, int, int, int], width: int, height: int) -> bool:
        """Whether a band of ink is a horizontal rule.

        Args:
            line: The ``(top, bottom, left, right)`` bounds of the band.
            width: The width of the page in pixels.
            height: The height of the page in pixels.

        Returns:
            ``True`` when the band is wide and thin.
        """
        top, bottom, left, right = line
        thickness = bottom - top
        max_thickness = max(2, round(_RULE_MAX_THICKNESS * height))
        return (right - left) >= _RULE_MIN_WIDTH * width and thickness <= max_thickness

    def _is_separated(self, ink: NDArray[np.bool_], top: int, width: int, height: int) -> bool:
        """Whether the footnote zone is separated from the body of the page.

        Args:
            ink: The mask of the ink of the page.
            top: The first row of the footnote zone.
            width: The width of the page in pixels.
            height: The height of the page in pixels.

        Returns:
            ``True`` when a rule or a clear gap stands between the body and
            the footnotes.
        """
        profile = ink[:top].sum(axis=1)
        body: list[tuple[int, int]] = []
        rule_below = False
        for start, end in _runs(profile > 0):
            band = ink[start:end]
            inked = np.flatnonzero(band.any(axis=0))
            if inked.size == 0:
                continue
            is_rule = int(inked[-1]) - int(
                inked[0]
            ) >= _RULE_MIN_WIDTH * width and end - start <= max(
                2, round(_RULE_MAX_THICKNESS * height)
            )
            if is_rule:
                if body:
                    rule_below = True
                continue
            body.append((start, end))
            rule_below = False
        if not body:
            return False
        if rule_below:
            return True
        gap = top - body[-1][1]
        spacings = [second[0] - first[0] for first, second in itertools.pairwise(body)]
        leading = self._median(spacings)
        needed = max(3, round(_FOOTNOTE_GAP_FACTOR * leading), round(_FOOTNOTE_MIN_GAP * height))
        return gap >= needed

    def _median(self, values: list[int]) -> float:
        """Return the median of a list of numbers, or zero when it is empty."""
        if not values:
            return 0.0
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2 == 1:
            return float(ordered[middle])
        return (ordered[middle - 1] + ordered[middle]) / 2.0
