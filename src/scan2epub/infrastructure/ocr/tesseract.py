"""Tesseract OCR adapter.

Tesseract is the default engine: it is Apache-2.0 licensed, runs on a plain
CPU and is the only engine that is fast enough for a 800-page book without a
GPU. It is noticeably weaker on historical type, which is exactly why the
project also ships vision-language engines and an LLM corrector.
"""

# pytesseract does not ship a `py.typed` marker, so the types of its API are
# unknown to the type checker. The rest of the code base stays strict.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false
# pyright: reportArgumentType=false

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytesseract
from pytesseract import Output

from scan2epub.domain.models import BBox, BlockKind, PageImage, TextBlock
from scan2epub.errors import EngineNotAvailableError, OcrError

__all__ = ["TesseractOcrEngine", "available_languages", "tesseract_version"]

#: Locations where the Windows installer puts the binary.
_WINDOWS_CANDIDATES = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


def _configure_binary() -> None:
    r"""Point pytesseract at the Tesseract binary, if it is not on ``PATH``.

    pytesseract defaults to the bare name ``tesseract``, which only works
    when the binary is in the ``PATH``. On Windows the installer puts it in
    ``C:\Program Files\Tesseract-OCR``, which is usually not in the
    ``PATH`` of a terminal.
    """
    if shutil.which("tesseract"):
        return
    for candidate in _WINDOWS_CANDIDATES:
        if candidate.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return


def tesseract_version() -> str | None:
    """Return the version of the installed Tesseract, or ``None``."""
    _configure_binary()
    try:
        raw = pytesseract.get_tesseract_version()
    except Exception:  # pragma: no cover - depends on the environment
        return None
    return str(raw)


def available_languages() -> list[str]:
    """Return the language data available to Tesseract."""
    _configure_binary()
    try:
        languages = pytesseract.get_languages(config="")
    except Exception:  # pragma: no cover - depends on the environment
        return []
    return sorted(str(language) for language in languages)


class TesseractOcrEngine:
    """Recognise pages with Tesseract.

    Attributes:
        name: The engine identifier used in the configuration file.
    """

    name = "tesseract"

    def __init__(
        self,
        *,
        lang: str = "spa",
        oem: int = 1,
        psm: int = 3,
        tessdata_dir: Path | None = None,
        timeout: int = 180,
    ) -> None:
        """Initialise the engine.

        Args:
            lang: Tesseract language(s), e.g. ``"spa"`` or ``"spa+eng"``.
                Use ``spa_old`` for Spanish books printed before 1900.
            oem: Tesseract OCR engine mode.
            psm: Tesseract page segmentation mode.
            tessdata_dir: Directory holding the ``*.traineddata`` files.
            timeout: Maximum number of seconds allowed for a single page.
        """
        self.lang = lang
        self.oem = oem
        self.psm = psm
        self.tessdata_dir = Path(tessdata_dir) if tessdata_dir else None
        self.timeout = timeout
        _configure_binary()
        if shutil.which("tesseract") is None and not (
            getattr(pytesseract.pytesseract, "tesseract_cmd", "")
            and Path(pytesseract.pytesseract.tesseract_cmd).is_file()
        ):
            raise EngineNotAvailableError(
                "Tesseract was not found. Install it and make sure 'tesseract' is on "
                "PATH, or pick another engine with --ocr."
            )

    def describe(self) -> dict[str, object]:
        """Return the settings that change the result of the recognition."""
        return {
            "engine": self.name,
            "lang": self.lang,
            "oem": self.oem,
            "psm": self.psm,
            "tessdata_dir": str(self.tessdata_dir) if self.tessdata_dir else None,
        }

    def _config(self) -> str:
        """Return the Tesseract command line configuration."""
        parts = [f"--oem {self.oem}", f"--psm {self.psm}"]
        tessdata = self.tessdata_dir
        if tessdata is None:
            prefix = os.environ.get("TESSDATA_PREFIX")
            # TESSDATA_PREFIX may point either at the directory that holds
            # the language files or at its parent.
            if prefix:
                candidate = Path(prefix)
                if (candidate / "eng.traineddata").is_file() or any(
                    candidate.glob("*.traineddata")
                ):
                    tessdata = candidate
                elif (candidate / "tessdata").is_dir():
                    tessdata = candidate / "tessdata"
        if tessdata is not None:
            # pytesseract splits the configuration on spaces, so the path
            # must not be quoted.
            parts.append(f"--tessdata-dir {tessdata}")
        return " ".join(parts)

    def recognize(self, image: PageImage) -> list[TextBlock]:
        """Recognise the text of a page.

        Args:
            image: The page to read.

        Returns:
            The text blocks of the page, in reading order. Every block keeps
            its physical lines so that the cleaner can repair hyphenation.

        Raises:
            OcrError: If Tesseract fails on the page.
        """
        try:
            raw = pytesseract.image_to_data(
                str(image.path),
                lang=self.lang,
                config=self._config(),
                output_type=Output.DICT,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise OcrError(f"Tesseract failed on page {image.index + 1}: {exc}") from exc
        if not isinstance(raw, dict):
            raise OcrError(f"Tesseract returned an unexpected result for page {image.index + 1}")
        data: dict[str, list[object]] = {
            str(key): list(value) if isinstance(value, list) else [value]
            for key, value in raw.items()
        }
        return self._to_blocks(data, image)

    def _to_blocks(self, data: dict[str, list[object]], image: PageImage) -> list[TextBlock]:
        """Convert the Tesseract data dictionary into text blocks."""
        levels = [int(value) for value in data.get("level", [])]
        texts = [str(value) for value in data.get("text", [])]
        confs = [float(value) for value in data.get("conf", [])]
        lefts = [int(value) for value in data.get("left", [])]
        tops = [int(value) for value in data.get("top", [])]
        widths = [int(value) for value in data.get("width", [])]
        heights = [int(value) for value in data.get("height", [])]
        block_nums = [int(value) for value in data.get("block_num", [])]
        par_nums = [int(value) for value in data.get("par_num", [])]
        line_nums = [int(value) for value in data.get("line_num", [])]

        # Group the words into (block, paragraph) groups, preserving order.
        groups: dict[tuple[int, int], list[int]] = {}
        for position, level in enumerate(levels):
            if level != 5:  # 5 == word
                continue
            if not texts[position].strip():
                continue
            key = (block_nums[position], par_nums[position])
            groups.setdefault(key, []).append(position)

        blocks: list[TextBlock] = []
        for order, key in enumerate(sorted(groups)):
            positions = groups[key]
            lines: list[str] = []
            current_line: list[str] = []
            current_line_num: int | None = None
            min_left = min_top = 10**9
            max_right = max_bottom = 0
            confidences: list[float] = []

            for position in positions:
                line_num = line_nums[position]
                if current_line_num is None:
                    current_line_num = line_num
                elif line_num != current_line_num:
                    lines.append(" ".join(current_line))
                    current_line = []
                    current_line_num = line_num
                current_line.append(texts[position].strip())
                confidences.append(confs[position])
                min_left = min(min_left, lefts[position])
                min_top = min(min_top, tops[position])
                max_right = max(max_right, lefts[position] + widths[position])
                max_bottom = max(max_bottom, tops[position] + heights[position])
            if current_line:
                lines.append(" ".join(current_line))

            valid = [value for value in confidences if value >= 0]
            confidence = sum(valid) / len(valid) / 100.0 if valid else 0.0
            bbox = BBox.from_pixels(
                min_left,
                min_top,
                max_right - min_left,
                max_bottom - min_top,
                image.width,
                image.height,
            )
            blocks.append(
                TextBlock(
                    lines=tuple(lines),
                    bbox=bbox,
                    confidence=confidence,
                    kind=BlockKind.BODY,
                    order=order,
                    page=image.index,
                )
            )
        return blocks
