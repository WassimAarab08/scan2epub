#!/usr/bin/env python
"""Build the evaluation corpus of public-domain books.

The corpus holds pages of books whose copyright has expired, together with
their reference transcription. The text comes from Project Gutenberg; the
pages are rendered as scans, with the typography of the period: the long s, the
ligatures, a running head, a folio and a footnote.

The reference transcription is the text **as it should be read**: the long s
normalised, the ligatures expanded, the running head and the folio removed.
That is exactly what the deterministic cleaner produces, so the evaluation
measures the whole chain.

Usage::

    uv run python scripts/fetch_samples.py
    uv run python scripts/fetch_samples.py --book es_don_quijote_1605
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

USER_AGENT = "scan2epub/0.1 (+https://github.com/WassimAarab08/scan2epub)"

#: The books of the corpus.
BOOKS: tuple[dict[str, object], ...] = (
    {
        "name": "es_don_quijote_1605",
        "gutenberg_id": 2000,
        "title": "Don Quijote",
        "author": "Miguel de Cervantes Saavedra",
        "year": "1605",
        "language": "es",
        "running_head": "DON QUIJOTE DE LA MANCHA",
        "ocr_language": "spa",
        "pages": 12,
    },
    {
        "name": "en_frederick_douglass_1845",
        "gutenberg_id": 23,
        "title": "Narrative of the Life of Frederick Douglass",
        "author": "Frederick Douglass",
        "year": "1845",
        "language": "en",
        "running_head": "THE LIFE OF FREDERICK DOUGLASS",
        "ocr_language": "eng",
        "pages": 12,
    },
    {
        "name": "en_the_awakening_1899",
        "gutenberg_id": 160,
        "title": "The Awakening",
        "author": "Kate Chopin",
        "year": "1899",
        "language": "en",
        "running_head": "THE AWAKENING",
        "ocr_language": "eng",
        "pages": 12,
    },
)

#: The lines of the licence of Project Gutenberg.
GUTENBERG_START = "*** START OF TH"
GUTENBERG_END = "*** END OF TH"

#: The words that the old Spanish printing used with the long s.
_LONG_S_WORDS = (
    "same",
    "sino",
    "solo",
    "sobre",
    "sujeto",
    "sentido",
    "siglo",
    "sino",
    "segun",
    "sesenta",
    "siete",
    "siempre",
    "siendo",
    "saber",
    "servir",
    "cosa",
    "cosa",
)


@dataclass
class _Book:
    """A book of the corpus."""

    name: str
    gutenberg_id: int
    title: str
    author: str
    year: str
    language: str
    running_head: str
    ocr_language: str
    pages: int
    paragraphs: list[str] = field(default_factory=list)


def _download(book: _Book) -> str:
    """Download the text of a book from Project Gutenberg.

    The text of the old Spanish books is often in Latin-1, so the decoding
    falls back to `cp1252` when the file is not valid UTF-8.
    """
    url = f"https://www.gutenberg.org/cache/epub/{book.gutenberg_id}/pg{book.gutenberg_id}.txt"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    print(f"  downloading {url}")
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        raw = response.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        print("  the file is not UTF-8, decoding it as cp1252")
        return raw.decode("cp1252", "replace")


def _extract_paragraphs(text: str, wanted: int) -> list[str]:
    """Extract the paragraphs of the body of a book."""
    start = text.find(GUTENBERG_START)
    end = text.find(GUTENBERG_END)
    body = text[start:end] if start != -1 and end != -1 else text
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", body):
        cleaned = " ".join(block.split())
        if len(cleaned) < 120:
            continue
        if cleaned.startswith("*") or cleaned.lower().startswith(("chapter", "part", "book ")):
            continue
        paragraphs.append(cleaned)
        if len(paragraphs) >= wanted:
            break
    return paragraphs


def _to_old_typography(text: str, seed: int) -> str:
    """Write a text the way that the old printers did.

    The long s is used everywhere but at the end of a word, and the two
    ligatures of the Spanish printing are used where they belong.
    """
    rng = random.Random(seed)

    def long_s(match: re.Match[str]) -> str:
        word = match.group(0)
        if word.endswith("s") and len(word) > 2:
            return word
        if word.lower() in _LONG_S_WORDS or rng.random() < 0.55:
            return word[0] + "ſ" + word[1:]
        return word

    result = re.sub(r"[A-Za-zÀ-ÿ'\u00C0-\u017F]+", long_s, text)
    # The ligature of "fi" and the one of "fl".
    result = result.replace("fi", "\ufb01").replace("fl", "\ufb02")
    # The old printing used a "u" where the modern one has a "v".
    return re.sub(r"\b([aeiou\u00E0-\u00EF]+)v", r"\1u", result)


def _render(
    lines: list[str],
    path: Path,
    *,
    font_path: Path,
    running_head: str,
    folio: str,
    footnote: str | None,
    seed: int,
) -> None:
    """Render a page as a scan."""
    from PIL import Image, ImageDraw, ImageFont

    rng = random.Random(seed)
    width, height = 1240, 1754
    margin_left, margin_right = 150, 130
    paper = 238
    image = Image.new("L", (width, height), paper)
    draw = ImageDraw.Draw(image)
    body_font = ImageFont.truetype(str(font_path), 30)
    head_font = ImageFont.truetype(str(font_path), 24)
    small_font = ImageFont.truetype(str(font_path), 21)

    draw.text((margin_left, 70), running_head, font=head_font, fill=45)

    y = 150
    for line in lines:
        if y > height - 250:
            break
        draw.text((margin_left, y), line, font=body_font, fill=22)
        y += 44

    if footnote:
        draw.line(
            [(margin_left, height - 300), (width - margin_right, height - 300)], fill=90, width=1
        )
        draw.text((margin_left, height - 285), footnote, font=small_font, fill=40)

    draw.text((margin_left, height - 150), folio, font=small_font, fill=45)

    # Tilt the page and add the dust of the paper.
    image = image.rotate(rng.uniform(-1.4, 1.4), resample=Image.BICUBIC, fillcolor=paper)
    draw = ImageDraw.Draw(image)
    for offset in range(10):
        draw.rectangle(
            [offset, offset, width - 1 - offset, height - 1 - offset], outline=40 + offset * 3
        )
    pixels = image.load()
    assert pixels is not None
    for _ in range(40_000):
        x = rng.randrange(width)
        y = rng.randrange(height)
        pixels[x, y] = max(0, min(255, pixels[x, y] + rng.randint(-20, 8)))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def _wrap_text(text: str, width: int = 82) -> list[str]:
    """Break a text into the lines of a printed page."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _font() -> Path | None:
    """Return a serif font of the system."""
    for candidate in (
        Path("C:/Windows/Fonts/times.ttf"),
        Path("C:/Windows/Fonts/georgia.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
    ):
        if candidate.is_file():
            return candidate
    return None


def _source_markdown(book: _Book) -> str:
    """Return the provenance of a book."""
    source = (
        f"[Project Gutenberg, eBook {book.gutenberg_id}]"
        f"(https://www.gutenberg.org/ebooks/{book.gutenberg_id})"
    )
    licence = (
        "Public domain in the United States; the original work is in the "
        "public domain in the European Union."
    )
    return f"""# {book.title}

| | |
| --- | --- |
| Author | {book.author} |
| Year | {book.year} |
| Language | {book.language} |
| Source | {source} |
| Licence | {licence} |
| OCR language | `{book.ocr_language}` |

## What these pages are

The **text** is the real, public-domain text of the work, taken from Project
Gutenberg. The **pages** are rendered by
[`scripts/fetch_samples.py`](../scripts/fetch_samples.py) as they would have
been printed: the long s, the ligatures, the running head, the folio and a
footnote.

They are not photographs of a book. They are synthetic pages that reproduce
the *typographical* problems of an old book, so that the corpus can be
versioned in the repository and the evaluation can run everywhere, without
scanning anything.

## The reference transcription

`reference.txt` holds the text as it should be read: the long s normalised,
the ligatures expanded, the running head and the folio removed, and the
footnote kept. It is what the deterministic cleaner must produce, so the
evaluation measures the whole chain and not only the recognition.
"""


def build(book: _Book, target: Path) -> None:
    """Build the directory of one book of the corpus."""
    font_path = _font()
    if font_path is None:
        raise SystemExit("No serif font was found on this system.")

    print(f"[{book.name}]")
    text = _download(book)
    paragraphs = _extract_paragraphs(text, book.pages * 8)
    if not paragraphs:
        raise SystemExit(f"  no paragraph could be extracted from {book.name}")

    directory = target / book.name
    pages_dir = directory / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # The text of the book, broken into the lines of a printed page.
    all_lines: list[str] = []
    for paragraph in paragraphs:
        all_lines.extend(_wrap_text(paragraph))

    lines_per_page = 28
    reference: list[str] = []
    page_number = 0
    for start in range(0, len(all_lines), lines_per_page):
        if page_number >= book.pages:
            break
        chunk = all_lines[start : start + lines_per_page]
        old = _to_old_typography(" ".join(chunk), seed=page_number + book.gutenberg_id)
        old_lines = _wrap_text(old, width=82)
        footnote = (
            f"{page_number + 1} Nota del autor sobre la imprenta y sus costes."
            if page_number % 4 == 3
            else None
        )
        _render(
            old_lines,
            pages_dir / f"{page_number + 1:03d}.png",
            font_path=font_path,
            running_head=book.running_head,
            folio=f"— {book.gutenberg_id + page_number} —",
            footnote=footnote,
            seed=page_number + 7,
        )
        # The reference is the text as it should be read: the running head
        # and the folio are furniture, the footnote is content.
        reference.extend(chunk)
        if footnote:
            reference.append(footnote)
        page_number += 1

    (directory / "reference.txt").write_text(" ".join(reference) + "\n", encoding="utf-8")
    (directory / "SOURCE.md").write_text(_source_markdown(book), encoding="utf-8")
    print(f"  {page_number} pages, {len(reference)} lines")


def main() -> int:
    """Build the corpus."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=str(ROOT / "samples"), help="Where to write it.")
    parser.add_argument("--book", action="append", help="Only this book. May be repeated.")
    arguments = parser.parse_args()

    target = Path(arguments.target)
    target.mkdir(parents=True, exist_ok=True)

    wanted = set(arguments.book or [])
    for entry in BOOKS:
        name = str(entry["name"])
        if wanted and name not in wanted:
            continue
        build(
            _Book(
                name=name,
                gutenberg_id=int(entry["gutenberg_id"]),  # type: ignore[arg-type]
                title=str(entry["title"]),
                author=str(entry["author"]),
                year=str(entry["year"]),
                language=str(entry["language"]),
                running_head=str(entry["running_head"]),
                ocr_language=str(entry["ocr_language"]),
                pages=int(entry["pages"]),  # type: ignore[arg-type]
            ),
            target,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
