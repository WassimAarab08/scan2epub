"""PDF page source based on `pypdfium2` (PDFium, BSD-3-Clause).

PDFium is used instead of PyMuPDF because the latter is AGPL-licensed. The
adapter renders every page to a PNG file on disk so that the rest of the
pipeline never has to hold more than one page in memory.
"""

# pypdfium2 does not ship a `py.typed` marker, so the types of its API are
# unknown to the type checker. The rest of the code base stays strict.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false
# pyright: reportArgumentType=false

from __future__ import annotations

from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image

from scan2epub.domain.models import PageImage
from scan2epub.errors import InputError, PipelineError

__all__ = ["PdfiumPageSource", "ink_ratio"]

#: A page is considered blank when less than this fraction of its pixels
#: contains ink.
BLANK_INK_THRESHOLD = 0.004


def ink_ratio(image: Image.Image) -> float:
    """Return the fraction of the page that contains ink.

    The image is downscaled first, which makes the computation cheap and
    robust against single stray pixels.
    """
    grayscale = image.convert("L")
    grayscale.thumbnail((600, 600))
    data = np.asarray(grayscale, dtype=np.uint8)
    if data.size == 0:
        return 0.0
    # 250 is well above the paper tone of a scanned page.
    return float(np.count_nonzero(data < 200)) / float(data.size)


class PdfiumPageSource:
    """Render a PDF into PNG pages with `pypdfium2`."""

    def __init__(self, pdf_path: Path, *, dpi: int = 300, out_dir: Path | None = None) -> None:
        """Initialise the source.

        Args:
            pdf_path: The PDF file to read.
            dpi: Resolution of the rendered pages.
            out_dir: Directory where the PNG pages are written. Defaults to
                ``<pdf stem>-pages`` next to the PDF.

        Raises:
            InputError: If the file does not exist, is not a PDF, is
                encrypted or has no pages.
        """
        self.pdf_path = Path(pdf_path)
        self.dpi = dpi
        self.out_dir = Path(out_dir) if out_dir else self.pdf_path.with_suffix(".pages")
        if not self.pdf_path.is_file():
            raise InputError(
                f"The file {self.pdf_path} does not exist. "
                "Check the path, or use --help to see the options."
            )
        if self.pdf_path.stat().st_size == 0:
            raise InputError(
                f"The file {self.pdf_path} is empty. A scanned book needs at least one page."
            )
        self._check_readable()

    def _check_readable(self) -> None:
        """Check that the PDF can be opened, and say why when it cannot."""
        try:
            document = pdfium.PdfDocument(str(self.pdf_path))
        except Exception as exc:
            raise InputError(
                f"The file {self.pdf_path} could not be opened as a PDF ({exc}). "
                "If it is a scan, make sure that it is a PDF and not an image."
            ) from exc
        try:
            try:
                count = len(document)
            except Exception as exc:
                raise InputError(
                    f"The PDF {self.pdf_path} is encrypted or damaged ({exc}). "
                    "Remove the password, or scan the pages again."
                ) from exc
            if count == 0:
                raise InputError(
                    f"The PDF {self.pdf_path} has no pages. A scanned book needs at least one page."
                )
        finally:
            document.close()

    def pages(self) -> list[PageImage]:
        """Render every page of the PDF.

        Returns:
            One :class:`PageImage` per page, in document order.

        Raises:
            InputError: If a page cannot be rendered.
            PipelineError: If the document cannot be opened.
        """
        self.out_dir.mkdir(parents=True, exist_ok=True)
        scale = self.dpi / 72.0
        pages: list[PageImage] = []
        try:
            document = pdfium.PdfDocument(str(self.pdf_path))
        except Exception as exc:  # pragma: no cover - checked in __init__
            raise PipelineError(f"Cannot open PDF {self.pdf_path}: {exc}") from exc

        try:
            for index in range(len(document)):
                page = document[index]
                try:
                    bitmap = page.render(scale=scale)
                    image: Image.Image = bitmap.to_pil().convert("L")
                except Exception as exc:
                    raise InputError(
                        f"The page {index + 1} of {self.pdf_path} could not be rendered "
                        f"({exc}). The file may be damaged; try to open it in a reader."
                    ) from exc
                path = self.out_dir / f"page-{index + 1:05d}.png"
                image.save(path, format="PNG", optimize=True)
                blank = ink_ratio(image) < BLANK_INK_THRESHOLD
                pages.append(
                    PageImage(
                        index=index,
                        path=path,
                        width=image.width,
                        height=image.height,
                        is_blank=blank,
                    )
                )
                page.close()
        finally:
            document.close()
        return pages

    def page_count(self) -> int:
        """Return the number of pages of the PDF without rendering them."""
        document = pdfium.PdfDocument(str(self.pdf_path))
        try:
            return len(document)
        finally:
            document.close()

    def estimated_size(self) -> tuple[int, int]:
        """Return the pixel size of a rendered page, without rendering it."""
        document = pdfium.PdfDocument(str(self.pdf_path))
        try:
            if len(document) == 0:
                return (0, 0)
            width, height = document[0].get_size()
            return (
                round(width * scale_of(self.dpi)),
                round(height * scale_of(self.dpi)),
            )
        finally:
            document.close()


def scale_of(dpi: int) -> float:
    """Return the PDF user-space scale factor for a given resolution."""
    return dpi / 72.0
