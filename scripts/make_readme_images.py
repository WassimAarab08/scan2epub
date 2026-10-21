"""Generate the before/after images used in the README.

The "before" image is a synthetic page that imitates an 18th-century Spanish
book: a running head, a folio, a long s, ligatures, words broken by a hyphen
at the end of a line, a footnote, skew, noise and a dark scan border.

The "after" image is the same content as it appears in the generated EPUB,
rendered with the stylesheet of the book.

Run it with::

    uv run python scripts/make_readme_images.py
"""

from __future__ import annotations

import random
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

OUTPUT = ROOT / "docs" / "images"
WORK = ROOT / "tmp" / "readme-images"

RUNNING_HEAD = "HISTORIA DE LA IMPRENTA EN ESPAÑA"

PARAGRAPH = [
    "El hombre que escribe con la letra larga, llamada por los",
    "impresores letra ſigma, no ſabe que la ſ final de la palabra",
    "ſe escribia de otra manera que la inicial, y que por eſo el",
    "texto de eſte libro aparece con muchas ſ y con ligaduras, como",
    "las que ſe ven en la palabra fi-ca, y con una paciencia que los",
    "tipógrafos de aquel tiempo no podian imaginar, y que los",
    "lectores de hoy encuentran muy dificil de seguir, y que",
    "requieren de una gran im-",
    "prenta de Madrid para poder entender lo que dicen.",
]

CONTINUED = [
    "El ſegundo capi-",
    "tulo trata de los dos tipos de letra que uſaron los",
    "impresores, y de las diferencias que hay entre ellos, y de",
    "la manera en que cada uno de ellos conſideraba la página.",
]

FOOTNOTE = "1 Nota del autor ſobre la imprenta y ſus costes."


def _font(size: int) -> ImageFont.FreeTypeFont:
    """Return the serif font used for the illustrations."""
    for candidate in (
        Path("C:/Windows/Fonts/times.ttf"),
        Path("C:/Windows/Fonts/georgia.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
    ):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    raise SystemExit("No serif font was found on this system.")


def _render_page(path: Path) -> Path:
    """Render the "before" image: a degraded page of an old book."""
    width, height = 1400, 1900
    paper = 236
    image = Image.new("L", (width, height), paper)
    draw = ImageDraw.Draw(image)
    body_font = _font(40)
    small_font = _font(30)
    title_font = _font(44)

    draw.text((150, 110), RUNNING_HEAD, font=small_font, fill=45)
    draw.text((150, 205), "CAPITULO PRIMERO", font=title_font, fill=25)
    y = 300
    for line in PARAGRAPH:
        draw.text((150, y), line, font=body_font, fill=20)
        y += 56
    y += 20
    for line in CONTINUED:
        draw.text((150, y), line, font=body_font, fill=20)
        y += 56
    draw.text((150, height - 230), FOOTNOTE, font=small_font, fill=35)
    draw.text((150, height - 150), "— 42 —", font=small_font, fill=35)

    # Tilt the page, as a book that has been scanned lying down would be.
    image = image.rotate(1.4, resample=Image.BICUBIC, fillcolor=paper)

    # Add the dark frame of the scanner.
    draw = ImageDraw.Draw(image)
    for offset in range(14):
        draw.rectangle(
            [offset, offset, image.width - 1 - offset, image.height - 1 - offset],
            outline=38 + offset * 2,
        )

    # Add the dust and the foxing of an old paper.
    rng = random.Random(20261021)
    pixels = image.load()
    assert pixels is not None
    for _ in range(90_000):
        x = rng.randrange(image.width)
        y = rng.randrange(image.height)
        shade = max(0, min(255, pixels[x, y] + rng.randint(-26, 10)))
        pixels[x, y] = shade
    for _ in range(140):
        cx = rng.randrange(40, image.width - 40)
        cy = rng.randrange(40, image.height - 40)
        radius = rng.randint(3, 14)
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            outline=170,
        )
    image = image.filter(ImageFilter.GaussianBlur(0.5))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)
    return path


def _clean_text() -> str:
    """Return the text of the page as the cleaner produces it.

    The long s becomes a plain s, the ligatures are expanded, the words
    broken by a hyphen at the end of a line are rejoined, the running head
    and the folio are gone and the lines are gathered into paragraphs.
    """
    return (
        "El hombre que escribe con la letra larga, llamada por los "
        "impresores letra sigma, no sabe que la s final de la palabra "
        "se escribia de otra manera que la inicial, y que por eso el "
        "texto de este libro aparece con muchas s y con ligaduras, como "
        "las que se ven en la palabra fica, y con una paciencia que los "
        "tipógrafos de aquel tiempo no podian imaginar, y que los "
        "lectores de hoy encuentran muy dificil de seguir, y que "
        "requieren de una gran imprenta de Madrid para poder entender lo "
        "que dicen. El segundo capitulo trata de los dos tipos de letra "
        "que usaron los impresores, y de las diferencias que hay entre "
        "ellos, y de la manera en que cada uno de ellos consideraba la "
        "página."
    )


def _build_epub(path: Path) -> Path:
    """Write the EPUB that the pipeline produces for the page above."""
    from scan2epub.domain.models import BBox, BlockKind, Book, BookMetadata, Chapter, TextBlock
    from scan2epub.infrastructure.epub.writer import EpubWriter

    paragraphs = _clean_text().split(". ")
    blocks = tuple(
        TextBlock(
            lines=(paragraph + ("." if index < len(paragraphs) - 1 else ""),),
            bbox=BBox(0.1, 0.2, 0.9, 0.3),
            confidence=0.95,
            kind=BlockKind.BODY,
            order=index,
        )
        for index, paragraph in enumerate(paragraphs)
        if paragraph.strip()
    )
    book = Book(
        metadata=BookMetadata(
            title="Historia de la imprenta en España",
            author="Anonimo",
            language="es",
            year="1765",
        ),
        chapters=(
            Chapter(
                id="chapter-1",
                title="CAPITULO PRIMERO",
                level=1,
                start_page=0,
                end_page=0,
                blocks=blocks,
            ),
        ),
    )
    EpubWriter().write(book, path)
    return path


def _render_reader(epub: Path, out: Path) -> Path:
    """Render the "after" image: the EPUB read in a reader."""
    with zipfile.ZipFile(epub) as archive:
        stylesheet = archive.read("EPUB/styles/main.css").decode("utf-8")
        chapter = next(name for name in archive.namelist() if name.startswith("EPUB/text/chapter-"))
        body = archive.read(chapter).decode("utf-8")
    body = body[body.index("<body>") + len("<body>") : body.index("</body>")]

    page = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>scan2epub</title>
<style>
{stylesheet}
html {{ background: #e8e4dd; }}
body {{
  max-width: 34rem; margin: 0 auto; padding: 3rem 2.5rem 4rem;
  background: #fbfaf7; color: #1c1a17; box-shadow: 0 2px 24px rgba(0,0,0,.12);
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  font-size: 19px; line-height: 1.6;
}}
h1 {{ font-size: 1.35em; margin: 0 0 1.2em; font-variant: small-caps; letter-spacing: .04em; }}
p {{ margin: 0 0 .85em; }}
</style></head>
<body>{body}</body></html>
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


def _crop_reader_screenshot(path: Path) -> Path:
    """Trim the empty space around the page of the reader screenshot."""
    image = Image.open(path).convert("RGB")
    background = image.getpixel((4, 4))
    width, height = image.size
    pixels = image.load()
    assert pixels is not None

    def is_background(x: int, y: int) -> bool:
        pixel = pixels[x, y]
        return all(abs(pixel[i] - background[i]) < 12 for i in range(3))

    left, right, top, bottom = width, 0, height, 0
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            if not is_background(x, y):
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right <= left or bottom <= top:
        return path
    margin = 12
    cropped = image.crop(
        (
            max(0, left - margin),
            max(0, top - margin),
            min(width, right + margin),
            min(height, bottom + margin),
        )
    )
    cropped.save(path, format="PNG", optimize=True)
    return path


def main() -> int:
    """Generate the two images."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    before = _render_page(OUTPUT / "before.png")
    print(f"before -> {before}")

    epub = _build_epub(WORK / "after.epub")
    print(f"epub   -> {epub}")

    reader = _render_reader(epub, WORK / "after.html")
    print(f"reader -> {reader}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
