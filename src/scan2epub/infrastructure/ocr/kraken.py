"""Kraken OCR adapter.

Kraken is an external program, not a library: the adapter writes the page to
a temporary TIFF, calls ``kraken`` with an argument list — never with a shell
string — and parses the ALTO XML that the program writes. The ALTO document
carries the box of every line, so the geometry of the page is preserved.

The weights are **not** committed to the repository: Kraken downloads them on
demand the first time it reads a page.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image

from scan2epub.domain.models import BBox, BlockKind, PageImage, TextBlock
from scan2epub.errors import EngineNotAvailableError, OcrError

__all__ = ["KrakenOcrEngine"]

#: The message that explains how to install Kraken.
_INSTALL_MESSAGE = (
    "Kraken was not found. Install it with 'pip install kraken' (or with "
    "'conda install -c conda-forge kraken'), make sure the 'kraken' program is on "
    "PATH, or pick another engine with --ocr."
)


def _tag(element: ElementTree.Element) -> str:
    """Return the name of an element, without its namespace."""
    return element.tag.rsplit("}", 1)[-1]


def _number(value: str | None) -> int:
    """Return an integer, or zero when the value is missing or broken."""
    if value is None:
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def _geometry(element: ElementTree.Element) -> tuple[int, int, int, int]:
    """Return the box of a line, in pixels.

    Args:
        element: The element of the ALTO document.

    Returns:
        The ``(left, top, width, height)`` of the line.
    """
    return (
        _number(element.get("HPOS")),
        _number(element.get("VPOS")),
        _number(element.get("WIDTH")),
        _number(element.get("HEIGHT")),
    )


def _text_of(element: ElementTree.Element) -> tuple[str, float]:
    """Return the text of a line and its confidence.

    Args:
        element: The element of the ALTO document.

    Returns:
        The text of the line and the mean confidence of its words.
    """
    words: list[str] = []
    weights: list[float] = []
    for child in element.iter():
        if _tag(child) != "String":
            continue
        content = child.get("CONTENT")
        if content:
            words.append(content)
        confidence = child.get("WC")
        if confidence is not None:
            try:
                weights.append(float(confidence))
            except ValueError:
                continue
    mean = sum(weights) / len(weights) if weights else 1.0
    return " ".join(words), mean


def _lines(root: ElementTree.Element) -> list[ElementTree.Element]:
    """Return the text lines of an ALTO document.

    Args:
        root: The root of the ALTO document.

    Returns:
        The lines of the page, in reading order.
    """
    lines = [element for element in root.iter() if _tag(element) == "TextLine"]
    if lines:
        return lines
    return [element for element in root.iter() if _tag(element) == "TextBlock"]


class KrakenOcrEngine:
    """Recognise pages with the Kraken program.

    Attributes:
        name: The engine identifier used in the configuration file.
    """

    name = "kraken"

    def __init__(
        self,
        *,
        model: str = "10.5281/zenodo.2577813",
        binary: str = "kraken",
        timeout: int = 300,
    ) -> None:
        """Initialise the engine.

        Args:
            model: The recognition model Kraken uses. The weights are
                downloaded on demand.
            binary: The name of the Kraken program, or the path to it.
            timeout: Maximum number of seconds allowed for a single page.

        Raises:
            EngineNotAvailableError: If the Kraken program is not installed.
        """
        self.model = model
        self.binary = binary
        self.timeout = timeout
        if shutil.which(binary) is None:
            raise EngineNotAvailableError(_INSTALL_MESSAGE)

    def describe(self) -> dict[str, object]:
        """Return the settings that change the result of the recognition."""
        return {
            "engine": self.name,
            "model": self.model,
            "binary": self.binary,
        }

    def recognize(self, image: PageImage) -> list[TextBlock]:
        """Recognise the text of a page.

        Args:
            image: The page to read.

        Returns:
            The text blocks of the page, in reading order. Every block holds
            one line, with the box of that line.

        Raises:
            EngineNotAvailableError: If the Kraken program is not installed.
            OcrError: If the page cannot be read or Kraken fails.
        """
        program = shutil.which(self.binary)
        if program is None:
            raise EngineNotAvailableError(_INSTALL_MESSAGE)
        with tempfile.TemporaryDirectory(prefix="scan2epub-kraken-") as folder:
            work = Path(folder)
            source = work / "page.tif"
            result = work / "page.xml"
            self._write_tiff(image, source)
            self._run(program, source, result, image.index + 1)
            return self._to_blocks(result, image)

    def _write_tiff(self, image: PageImage, target: Path) -> None:
        """Write the page to a temporary TIFF file.

        Args:
            image: The page to read.
            target: The file to write.

        Raises:
            OcrError: If the page cannot be read.
        """
        try:
            with Image.open(image.path) as page:
                page.convert("L").save(target, format="TIFF")
        except OSError as exc:
            raise OcrError(f"Kraken cannot read the page {image.index + 1}: {exc}") from exc

    def _run(self, program: str, source: Path, result: Path, page: int) -> None:
        """Call Kraken and let it recognise the page.

        The program is called with an argument list and never through a
        shell, so that the name of the file cannot be interpreted.

        Args:
            program: The path of the Kraken program.
            source: The TIFF file to read.
            result: The ALTO file to write.
            page: The number of the page, for the error messages.

        Raises:
            EngineNotAvailableError: If the Kraken program disappeared.
            OcrError: If Kraken fails or takes too long.
        """
        command = [
            program,
            "-i",
            str(source),
            str(result),
            "-a",
            "binarize",
            "segment",
            "ocr",
            "-m",
            self.model,
        ]
        try:
            completed = subprocess.run(  # noqa: S603 - a fixed argument list, never a shell
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise EngineNotAvailableError(_INSTALL_MESSAGE) from exc
        except subprocess.TimeoutExpired as exc:
            raise OcrError(
                f"Kraken did not finish the page {page} in {self.timeout} seconds."
            ) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or "unknown error"
            raise OcrError(f"Kraken failed on the page {page}: {detail}")

    def _to_blocks(self, result: Path, image: PageImage) -> list[TextBlock]:
        """Convert the ALTO document of Kraken into text blocks.

        Args:
            result: The ALTO file to read.
            image: The page that was read.

        Returns:
            The text blocks of the page, in reading order.

        Raises:
            OcrError: If the ALTO document cannot be read.
        """
        try:
            tree = ElementTree.parse(result)  # noqa: S314 - Kraken writes this file itself
        except (OSError, ElementTree.ParseError) as exc:
            raise OcrError(
                f"Kraken produced an unreadable result for the page {image.index + 1}: {exc}"
            ) from exc
        blocks: list[TextBlock] = []
        for element in _lines(tree.getroot()):
            text, confidence = _text_of(element)
            if not text:
                continue
            left, top, width, height = _geometry(element)
            blocks.append(
                TextBlock(
                    lines=(text,),
                    bbox=BBox.from_pixels(left, top, width, height, image.width, image.height),
                    confidence=confidence,
                    kind=BlockKind.BODY,
                    order=len(blocks),
                    page=image.index,
                )
            )
        return blocks
