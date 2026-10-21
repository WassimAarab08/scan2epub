"""Test fixtures: synthetic books and scanned-looking pages.

The helpers here are deliberately dependency-free. The PDF writer produces a
real, valid PDF that uses the base-14 Times font, so the fixtures work on any
platform without shipping a font file.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from pathlib import Path

__all__ = [
    "BODY_PAGES",
    "FOLIO",
    "FOOTNOTE",
    "RUNNING_HEAD",
    "find_system_font",
    "make_scanned_image",
    "make_text_pdf",
]

#: The body of the synthetic book, one entry per page. The last line of a
#: page continues on the first line of the next one, and one word is broken
#: by a hyphen at the end of a line.
BODY_PAGES: tuple[tuple[str, ...], ...] = (
    (
        "El hombre que escribe con la letra larga, llamada por los",
        "impresores letra sigma, no sabe que la s final de la palabra",
        "se escribia de otra manera que la inicial, y que por eso el",
        "texto de este libro aparece con muchas s y con ligaduras, como",
        "las que se ven en la palabra fica, y con una paciencia que los",
        "tipografos de aquel tiempo no podian imaginar, y que los",
        "lectores de hoy encuentran muy dificil de seguir, y que",
        "requieren de una gran im-",
    ),
    (
        "prenta de Madrid para poder entender lo que dicen.",
        "El segunda capi-",
        "tulo trata de los dos tipos de letra que usaron los",
        "impresores, y de las diferencias que hay entre ellos.",
        "El tercero explica el uso de las abreviaturas, y acaba",
        "con una nota sobre el precio del papel y el de la tinta.",
    ),
    (
        "Este capitulo empieza con una definicion, y sigue con una",
        "explicacion de los motivos que tuvo el rey para fundar la",
        "imprenta, y de la manera en que se organizo el trabajo de",
        "los tipografos, que era un trabajo muy duro y muy mal",
        "pagado, y que sin embargo dejo un legado enorme, que",
        "llegamos hasta nosotros sin ninguna perdida, y que",
        "todavia hoy se puede leer con detenimiento y con",
        "paciencia, y con una letra que ya casi nadie usa, y que",
        "sin embargo es la que nos ha traido hasta aqui.",
    ),
)

#: A footnote printed at the bottom of every page.
FOOTNOTE = "1 Nota del autor sobre la imprenta y sus costes."

#: The running head printed at the top of every page.
RUNNING_HEAD = "HISTORIA DE LA IMPRENTA"

#: The page number printed at the bottom of every page.
FOLIO = "— 42 —"


def _escape_pdf_text(text: str) -> bytes:
    """Encode a text run for a PDF content stream."""
    encoded = text.encode("cp1252", errors="replace")
    out = bytearray(b"(")
    for byte in encoded:
        if byte in (0x28, 0x29, 0x5C):  # ( ) \
            out.append(0x5C)
        out.append(byte)
    out.append(0x29)
    return bytes(out)


def _build_pdf(pages: Sequence[Sequence[tuple[str, int]]]) -> bytes:
    """Build a PDF whose pages contain the given ``(text, y)`` lines.

    Args:
        pages: One sequence of ``(line, y_position)`` pairs per page.

    Returns:
        The bytes of the PDF file.
    """
    objects: list[bytes] = []

    page_count = len(pages)
    # Object numbering: 1 = catalog, 2 = pages, 3 = font,
    # then two objects per page (page + content stream).
    page_ids = [4 + 2 * index for index in range(page_count)]

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("latin-1"))
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman /Encoding /WinAnsiEncoding >>"
    )

    for index, lines in enumerate(pages):
        content = bytearray(b"BT\n")
        for text, y in lines:
            content += b"/F1 12 Tf\n"
            content += f"1 0 0 1 72 {y} Tm\n".encode("latin-1")
            content += _escape_pdf_text(text)
            content += b" Tj\n"
        content += b"ET\n"
        payload = bytes(content)

        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {page_ids[index] + 1} 0 R >>"
            ).encode("latin-1")
        )
        objects.append(
            b"<< /Length "
            + str(len(payload)).encode("latin-1")
            + b" >>\nstream\n"
            + payload
            + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("latin-1")
        out += payload
        out += b"\nendobj\n"

    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("latin-1")
    out += f"startxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    return bytes(out)


def make_text_pdf(path: Path, *, pages: int = 3) -> Path:
    """Write a synthetic book that looks like a printed page.

    Every page carries a running head and a folio, the body text contains
    words broken by a hyphen at the end of a line, and the last paragraph of
    a page continues on the next one.

    Args:
        path: Where the PDF is written.
        pages: The number of pages.

    Returns:
        The path of the written PDF.
    """
    page_lines: list[list[tuple[str, int]]] = []
    for page_index in range(pages):
        body = BODY_PAGES[page_index % len(BODY_PAGES)]
        lines: list[tuple[str, int]] = [(RUNNING_HEAD, 750)]
        if page_index == 0:
            lines.append(("CAPITULO PRIMERO", 705))
        y = 660
        for text in body:
            lines.append((text, y))
            y -= 26
        lines.append((FOOTNOTE, 110))
        lines.append((FOLIO, 60))
        page_lines.append(lines)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_build_pdf(page_lines))
    return path


def find_system_font() -> Path | None:
    """Return a serif TrueType font found on the system, if any."""
    candidates = (
        Path("C:/Windows/Fonts/times.ttf"),
        Path("C:/Windows/Fonts/georgia.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
        Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def make_scanned_image(
    path: Path,
    *,
    width: int = 1240,
    height: int = 1754,
    skew: float = 1.5,
    noise: float = 12.0,
    border: int = 18,
    seed: int = 7,
) -> Path | None:
    """Render a page that looks like a degraded scan.

    The page is rendered with a system font, then rotated, dirtied with noise
    and framed with a dark border.

    Args:
        path: Where the image is written.
        width: The width of the image.
        height: The height of the image.
        skew: The skew angle, in degrees.
        noise: The amount of noise added to the image.
        border: The width of the dark frame.
        seed: The random seed, for reproducible results.

    Returns:
        The path of the image, or ``None`` when no usable font was found.
    """
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    font_path = find_system_font()
    if font_path is None:
        return None

    rng = random.Random(seed)
    image = Image.new("L", (width, height), 244)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(str(font_path), 34)
        small = ImageFont.truetype(str(font_path), 26)
    except OSError:  # pragma: no cover - depends on the system
        return None

    draw.text((150, 90), RUNNING_HEAD, font=small, fill=40)
    y = 190
    for index in range(24):
        text = BODY_PAGES[0][index % len(BODY_PAGES[0])]
        draw.text((150, y), text[:70], font=font, fill=25)
        y += 52
    draw.text((150, height - 110), FOLIO, font=small, fill=40)

    if skew:
        image = image.rotate(skew, resample=Image.BICUBIC, fillcolor=244)
    if border:
        draw = ImageDraw.Draw(image)
        for offset in range(border):
            shade = 40 + offset
            draw.rectangle(
                [offset, offset, image.width - 1 - offset, image.height - 1 - offset],
                outline=shade,
            )

    if noise:
        pixels = image.load()
        assert pixels is not None
        for x in range(0, image.width, 2):
            for y in range(0, image.height, 2):
                value = max(0, min(255, pixels[x, y] + rng.randint(-noise, noise)))
                pixels[x, y] = value
        image = image.filter(ImageFilter.GaussianBlur(0.4))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return path


def rotation_matrix(angle_degrees: float) -> tuple[float, float, float, float]:
    """Return the affine matrix of a rotation, for the tests."""
    radians = math.radians(angle_degrees)
    return (
        math.cos(radians),
        -math.sin(radians),
        math.sin(radians),
        math.cos(radians),
    )
