"""Image pre-processing with OpenCV.

Old scans suffer from four problems that hurt OCR much more than they hurt
human readers: skew, uneven illumination, noise and black scan borders. This
module removes all four, in that order, using only OpenCV and NumPy.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path

import cv2
import numpy as np

from scan2epub.config import PreprocessConfig
from scan2epub.domain.models import PageImage

__all__ = ["OpenCvPreprocessor", "estimate_skew"]


def _first_light_row(ratios: np.ndarray, threshold: float) -> int | None:
    """Return the index of the first row that is not mostly dark."""
    light = np.flatnonzero(ratios < threshold)
    if light.size == 0:
        return None
    return int(light[0])


def _last_light_row(ratios: np.ndarray, threshold: float) -> int | None:
    """Return the index of the last row that is not mostly dark."""
    light = np.flatnonzero(ratios < threshold)
    if light.size == 0:
        return None
    return int(light[-1]) + 1


def estimate_skew(gray: np.ndarray) -> float:
    """Estimate the skew angle of a page, in degrees.

    The estimate is the median angle of the near-horizontal edges detected by
    the Hough transform, which is far more robust on old printed text than
    the bounding-box approach.

    Args:
        gray: Grayscale image as a 2D ``uint8`` array.

    Returns:
        The skew angle in degrees, positive when the text slopes downwards to
        the right. ``0.0`` when no reliable estimate could be computed.
    """
    height, width = gray.shape[:2]
    if height < 10 or width < 10:
        return 0.0

    # Work on a downscaled copy: Hough is expensive and the angle does not
    # depend on the resolution.
    scale = min(1.0, 1200.0 / max(width, height))
    if scale < 1.0:
        small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        small = gray

    _, small_width = small.shape[:2]
    blurred = cv2.GaussianBlur(small, (3, 3), 0)
    edges = cv2.Canny(blurred, 50, 150, apertureSize=3)
    min_length = max(30, small_width // 3)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180.0,
        threshold=80,
        minLineLength=min_length,
        maxLineGap=20,
    )
    if lines is None:
        return 0.0

    angles: list[float] = []
    # OpenCV 4 returns an (N, 1, 4) array and OpenCV 5 an (N, 4) one.
    for line in np.asarray(lines).reshape(-1, 4):
        x1, y1, x2, y2 = (int(value) for value in line)
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 or abs(dy) > 0.25 * abs(dx):
            # Not a near-horizontal line.
            continue
        angle = math.degrees(math.atan2(dy, dx))
        if -30.0 < angle < 30.0:
            angles.append(angle)
    if len(angles) < 3:
        return 0.0
    return float(statistics.median(angles))


class OpenCvPreprocessor:
    """Deskew, denoise, crop and binarise a page image."""

    def __init__(self, config: PreprocessConfig | None = None) -> None:
        """Initialise the preprocessor.

        Args:
            config: The pre-processing options. Defaults are used when omitted.
        """
        self.config = config or PreprocessConfig()

    def process(self, image: PageImage, out_dir: Path) -> PageImage:
        """Return a cleaned-up copy of ``image``.

        Args:
            image: The page to process.
            out_dir: Directory where the result is written.

        Returns:
            A new :class:`PageImage` pointing at the processed PNG. The
            original image is left untouched.
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        gray = cv2.imread(str(image.path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            raise ValueError(f"Cannot read page image: {image.path}")

        if self.config.deskew:
            angle = estimate_skew(gray)
            if abs(angle) > 0.1:
                gray = self._rotate(gray, angle)
        if self.config.crop_borders:
            gray = self._crop_borders(gray)
        if self.config.denoise:
            gray = self._denoise(gray)
        if self.config.binarize:
            gray = self._binarize(gray)

        out_path = out_dir / f"page-{image.index + 1:05d}.png"
        cv2.imwrite(str(out_path), gray)
        return PageImage(
            index=image.index,
            path=out_path,
            width=int(gray.shape[1]),
            height=int(gray.shape[0]),
            is_blank=image.is_blank,
        )

    def _rotate(self, gray: np.ndarray, angle: float) -> np.ndarray:
        """Rotate the page so that the text lines become horizontal."""
        height, width = gray.shape[:2]
        matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
        cos = abs(matrix[0, 0])
        sin = abs(matrix[0, 1])
        new_width = int(height * sin + width * cos)
        new_height = int(height * cos + width * sin)
        matrix[0, 2] += (new_width / 2.0) - (width / 2.0)
        matrix[1, 2] += (new_height / 2.0) - (height / 2.0)
        return cv2.warpAffine(
            gray,
            matrix,
            (new_width, new_height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255,
        )

    def _crop_borders(self, gray: np.ndarray) -> np.ndarray:
        """Remove the dark frame that surrounds most scanned pages."""
        height, width = gray.shape[:2]
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        dark = binary > 0

        # A scan border shows up as rows and columns that are almost entirely
        # dark. Removing them first makes the ink bounding box meaningful.
        row_ratio = dark.sum(axis=1) / float(width)
        column_ratio = dark.sum(axis=0) / float(height)
        top = _first_light_row(row_ratio, 0.6)
        bottom = _last_light_row(row_ratio, 0.6)
        left = _first_light_row(column_ratio, 0.6)
        right = _last_light_row(column_ratio, 0.6)
        if (
            top is not None
            and bottom is not None
            and left is not None
            and right is not None
            and bottom - top > 20
            and right - left > 20
        ):
            gray = gray[top:bottom, left:right]
            height, width = gray.shape[:2]
            binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
            dark = binary > 0
        band = max(2, round(min(height, width) * 0.01))
        binary[:band, :] = 0
        binary[height - band :, :] = 0
        binary[:, :band] = 0
        binary[:, width - band :] = 0

        coordinates = cv2.findNonZero(binary)
        if coordinates is None:  # type: ignore[reportUnnecessaryComparison]
            return gray
        if coordinates.size == 0:
            return gray
        x, y, box_width, box_height = cv2.boundingRect(coordinates)
        margin = self.config.crop_margin
        left = max(0, x - margin)
        top = max(0, y - margin)
        right = min(width, x + box_width + margin)
        bottom = min(height, y + box_height + margin)
        if right - left < 10 or bottom - top < 10:
            return gray
        if (right - left) * (bottom - top) > 0.98 * width * height:
            # Nothing meaningful was cropped.
            return gray
        return gray[top:bottom, left:right]

    def _denoise(self, gray: np.ndarray) -> np.ndarray:
        """Remove speckle noise while keeping the strokes intact."""
        median = cv2.medianBlur(gray, 3)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        return cv2.morphologyEx(median, cv2.MORPH_OPEN, kernel)

    def _binarize(self, gray: np.ndarray) -> np.ndarray:
        """Apply an adaptive threshold to remove uneven illumination."""
        block_size = self.config.binary_block_size
        if block_size % 2 == 0:
            block_size += 1
        return cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            block_size,
            self.config.binary_c,
        )
