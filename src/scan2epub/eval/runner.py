"""The evaluation of the OCR engines.

The evaluation measures how well an engine recognises a book, by comparing its
output with a reference transcription. It is the only way to tell whether a
change to the cleaning rules makes the books better or worse.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PIL import Image

from scan2epub.application.cache import FileCache, block_from_dict, block_to_dict
from scan2epub.application.stages.clean import clean_pages
from scan2epub.config import Config
from scan2epub.domain.models import PageContent, PageImage, TextBlock
from scan2epub.domain.ports import OcrEngine
from scan2epub.eval.metrics import character_error_rate, word_error_rate
from scan2epub.logging import get_logger

__all__ = ["SampleResult", "evaluate_sample", "render_markdown", "sample_directories"]

_LOGGER = get_logger(__name__)

#: The name of the file with the reference transcription.
REFERENCE_FILE = "reference.txt"

#: The name of the directory with the pages.
PAGES_DIR = "pages"


@dataclass(frozen=True, slots=True)
class SampleResult:
    """The result of the evaluation of one book with one engine."""

    engine: str
    sample: str
    cer: float
    wer: float
    seconds: float
    pages: int
    characters: int
    notes: tuple[str, ...] = ()

    @property
    def seconds_per_page(self) -> float:
        """The time that the engine took per page."""
        return self.seconds / self.pages if self.pages else 0.0


def sample_directories(samples_dir: Path) -> list[Path]:
    """Return the directories of the corpus that hold a reference.

    Args:
        samples_dir: The root of the corpus.

    Returns:
        The directories, sorted by name.
    """
    if not samples_dir.is_dir():
        return []
    return sorted(
        directory
        for directory in samples_dir.iterdir()
        if directory.is_dir() and (directory / REFERENCE_FILE).is_file()
    )


def _load_pages(sample: Path) -> list[PageImage]:
    """Return the pages of a sample."""
    pages_dir = sample / PAGES_DIR
    if not pages_dir.is_dir():
        return []
    pages: list[PageImage] = []
    for index, path in enumerate(sorted(pages_dir.glob("*.png"))):
        with Image.open(path) as image:
            width, height = image.size
        pages.append(PageImage(index=index, path=path, width=width, height=height))
    return pages


def evaluate_sample(
    sample: Path,
    engine: OcrEngine,
    *,
    work_dir: Path | None = None,
    cache: FileCache | None = None,
) -> SampleResult:
    """Evaluate one engine on one book.

    The engine recognises every page, the deterministic cleaner repairs the
    result, and the cleaned text is compared with the reference.

    Args:
        sample: The directory of the book.
        engine: The engine to evaluate.
        work_dir: Where the intermediate files are written.
        cache: An optional cache of the recognition results.

    Returns:
        The result of the evaluation.
    """
    reference = (sample / REFERENCE_FILE).read_text(encoding="utf-8")
    pages = _load_pages(sample)
    if not pages:
        return SampleResult(
            engine=engine.name,
            sample=sample.name,
            cer=1.0,
            wer=1.0,
            seconds=0.0,
            pages=0,
            characters=0,
            notes=("the sample has no pages",),
        )

    contents: list[PageContent] = []
    started = time.monotonic()
    for page in pages:
        blocks = _recognize(engine, page, work_dir, cache)
        contents.append(PageContent(index=page.index, blocks=tuple(blocks)))
    elapsed = time.monotonic() - started

    cleaned = clean_pages(contents, Config().clean)
    hypothesis = "\n\n".join(
        " ".join(block.text.split()) for page in cleaned.pages for block in page.blocks
    )
    return SampleResult(
        engine=engine.name,
        sample=sample.name,
        cer=character_error_rate(hypothesis, reference),
        wer=word_error_rate(hypothesis, reference),
        seconds=elapsed,
        pages=len(pages),
        characters=len(reference),
    )


def _recognize(
    engine: OcrEngine,
    page: PageImage,
    work_dir: Path | None,
    cache: FileCache | None,
) -> list[TextBlock]:
    """Recognise a page, using the cache when there is one."""
    if cache is None or work_dir is None:
        return list(engine.recognize(page))
    key = f"eval:{engine.name}:{page.index}:{page.path.stat().st_size}"
    cached = cache.get_json(key)
    if isinstance(cached, list):
        payloads = cast("list[object]", cached)
        return [
            block_from_dict(cast("dict[str, object]", payload))
            for payload in payloads
            if isinstance(payload, dict)
        ]
    blocks = list(engine.recognize(page))
    cache.put_json(key, [block_to_dict(block) for block in blocks])
    return blocks


def render_markdown(results: list[SampleResult]) -> str:
    """Render the results as a Markdown table.

    Args:
        results: The results of the evaluation.

    Returns:
        The Markdown table, with the header of the columns.
    """
    lines = [
        "| Book | Engine | CER ↓ | WER ↓ | Pages | s/page |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in sorted(results, key=lambda item: (item.sample, item.engine)):
        lines.append(
            f"| {result.sample} | {result.engine} | {result.cer:.4f} | {result.wer:.4f} | "
            f"{result.pages} | {result.seconds_per_page:.2f} |"
        )
    return "\n".join(lines) + "\n"
