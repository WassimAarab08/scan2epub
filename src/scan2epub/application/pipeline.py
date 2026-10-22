"""The conversion pipeline.

The pipeline is a sequence of pure stages connected by a cache. Every stage
receives explicit inputs and returns explicit outputs, which makes the whole
conversion testable without touching the filesystem beyond the page images.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from scan2epub.application.cache import (
    FileCache,
    block_from_dict,
    block_to_dict,
    hash_file,
    hash_json,
)
from scan2epub.application.progress import ProgressEvent, ProgressReporter
from scan2epub.application.stages.clean import CleanResult, clean_pages
from scan2epub.application.stages.structure import structure_book
from scan2epub.application.stages.validate import ValidationReport, validate_epub
from scan2epub.config import Config
from scan2epub.domain.models import (
    Book,
    BookMetadata,
    PageContent,
    PageImage,
    TextBlock,
)
from scan2epub.domain.ports import OcrEngine, PagePreprocessor, PageSource, TextCorrector
from scan2epub.errors import PipelineError
from scan2epub.infrastructure.epub.writer import EpubResult, EpubWriter
from scan2epub.logging import get_logger

__all__ = ["Pipeline", "PipelineResult"]

_LOGGER = get_logger(__name__)

#: Bumped whenever the shape of a cached artefact changes.
_CACHE_VERSION = "1"


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Everything a caller needs to know about a finished conversion."""

    book: Book
    epub_path: Path
    epub_size: int
    validation: ValidationReport
    clean: CleanResult
    epub: EpubResult
    page_count: int
    duration_seconds: float


class Pipeline:
    """Run the full conversion of a scanned document into an EPUB."""

    def __init__(
        self,
        *,
        source: PageSource,
        preprocessor: PagePreprocessor,
        ocr: OcrEngine,
        config: Config,
        work_dir: Path,
        corrector: TextCorrector | None = None,
        cache: FileCache | None = None,
        reporter: ProgressReporter | None = None,
    ) -> None:
        """Initialise the pipeline.

        Args:
            source: Produces the rasterised pages.
            preprocessor: Cleans up the page images.
            ocr: Recognises the text of the pages.
            config: The effective configuration.
            work_dir: Directory where the intermediate artefacts are written.
            corrector: An optional LLM post-corrector.
            cache: An optional artefact cache that makes the run resumable.
            reporter: An optional callable that receives the progress events.
        """
        self.source = source
        self.preprocessor = preprocessor
        self.ocr = ocr
        self.corrector = corrector
        self.config = config
        self.work_dir = Path(work_dir)
        self.cache = cache
        self.reporter = reporter

    # -- helpers --------------------------------------------------------

    def _emit(self, event: ProgressEvent) -> None:
        """Send a progress event to the reporter, if there is one."""
        if self.reporter is not None:
            self.reporter(event)

    def _ocr_cache_key(self, image: PageImage) -> str:
        """Return the cache key of the OCR result of a page.

        The key covers everything that can change the result: the content of
        the page, the settings of the engine and the pre-processing options.
        Two runs that differ in any of them never share their artefacts.
        """
        payload = {
            "version": _CACHE_VERSION,
            "engine": self._engine_fingerprint(),
            "page": hash_file(image.path),
            "config": hash_json({"preprocess": self.config.preprocess.model_dump()}),
        }
        return hash_json(payload)

    def _engine_fingerprint(self) -> dict[str, object]:
        """Return the settings of the OCR engine, for the cache key."""
        describe = getattr(self.ocr, "describe", None)
        if callable(describe):
            return dict(cast("dict[str, object]", describe()))
        return {"engine": getattr(self.ocr, "name", type(self.ocr).__name__)}

    # -- stages ---------------------------------------------------------

    def run(self, metadata: BookMetadata, output_path: Path) -> PipelineResult:
        """Convert the source document into an EPUB.

        Args:
            metadata: The metadata of the book.
            output_path: The destination ``.epub`` file.

        Returns:
            The result of the conversion.

        Raises:
            PipelineError: If a stage fails.
        """
        started = time.monotonic()
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # 1. Ingest -----------------------------------------------------
        self._emit(ProgressEvent(stage="ingest", message="Rendering the pages"))
        pages = self.source.pages()
        if not pages:
            raise PipelineError("The source document has no pages.")
        self._emit(
            ProgressEvent(stage="ingest", message="Pages rendered", total=len(pages), percent=100.0)
        )

        # 2. Pre-process ------------------------------------------------
        processed: list[PageImage] = []
        for page in pages:
            if page.is_blank:
                processed.append(page)
                continue
            processed.append(self.preprocessor.process(page, self.work_dir / "pages"))
            self._emit(
                ProgressEvent(
                    stage="preprocess",
                    page=page.index + 1,
                    total=len(pages),
                    percent=100.0 * (page.index + 1) / len(pages),
                )
            )

        # 3. OCR --------------------------------------------------------
        contents: list[PageContent] = []
        for page in processed:
            blocks = self._recognize(page)
            contents.append(PageContent(index=page.index, blocks=tuple(blocks)))
            self._emit(
                ProgressEvent(
                    stage="ocr",
                    page=page.index + 1,
                    total=len(pages),
                    percent=100.0 * (page.index + 1) / len(pages),
                    message=f"Page {page.index + 1} recognised",
                )
            )

        # 4. Deterministic cleaning -------------------------------------
        self._emit(ProgressEvent(stage="clean", message="Cleaning the text"))
        clean_result = clean_pages(contents, self.config.clean)
        self._emit(
            ProgressEvent(
                stage="clean",
                message="Text cleaned",
                total=len(pages),
                percent=100.0,
            )
        )

        # 5. Optional LLM post-correction ------------------------------
        if self.corrector is not None:
            self._emit(ProgressEvent(stage="correct", message="Correcting the text"))
            clean_result = self._correct(clean_result)

        # 6. Structure --------------------------------------------------
        self._emit(ProgressEvent(stage="structure", message="Detecting the chapters"))
        book = structure_book(clean_result.pages, metadata)
        self._emit(
            ProgressEvent(
                stage="structure",
                message="Chapters detected",
                total=len(book.chapters),
                percent=100.0,
            )
        )

        # 7. Write the EPUB ---------------------------------------------
        self._emit(ProgressEvent(stage="epub", message="Writing the EPUB"))
        writer = EpubWriter(language=metadata.language)
        epub_result = writer.write(book, Path(output_path))
        self._emit(ProgressEvent(stage="epub", message="EPUB written", total=1, percent=100.0))

        # 8. Validate ----------------------------------------------------
        validation = ValidationReport(ran=False, passed=True)
        if self.config.general.validate_epub:
            self._emit(ProgressEvent(stage="validate", message="Validating the EPUB"))
            validation = validate_epub(Path(output_path))
            self._emit(
                ProgressEvent(
                    stage="validate",
                    message="Validation finished",
                    total=1,
                    percent=100.0,
                )
            )

        return PipelineResult(
            book=book,
            epub_path=Path(output_path),
            epub_size=epub_result.size,
            validation=validation,
            clean=clean_result,
            epub=epub_result,
            page_count=len(pages),
            duration_seconds=time.monotonic() - started,
        )

    def _recognize(self, page: PageImage) -> list[TextBlock]:
        """Recognise a page, using the cache when possible."""
        if self.cache is None:
            return list(self.ocr.recognize(page))
        key = self._ocr_cache_key(page)
        cached = self.cache.get_json(key)
        if isinstance(cached, list):
            _LOGGER.debug("ocr.cache_hit", page=page.index + 1, engine=self.ocr.name)
            blocks: list[TextBlock] = []
            for payload in cast("list[object]", cached):
                if isinstance(payload, dict):
                    blocks.append(block_from_dict(cast("dict[str, object]", payload)))
            return blocks
        blocks = list(self.ocr.recognize(page))
        self.cache.put_json(key, [block_to_dict(block) for block in blocks])
        return blocks

    def _correct(self, result: CleanResult) -> CleanResult:
        """Run the LLM post-corrector over the cleaned pages."""
        corrector = self.corrector
        if corrector is None:
            return result
        pages: list[PageContent] = []
        for page in result.pages:
            correction = corrector.correct(page.blocks)
            pages.append(PageContent(index=page.index, blocks=tuple(correction.blocks)))
        return CleanResult(
            pages=tuple(pages),
            removed_running_heads=result.removed_running_heads,
            removed_page_numbers=result.removed_page_numbers,
            joined_hyphens=result.joined_hyphens,
            merged_paragraphs=result.merged_paragraphs,
            detected_footnotes=result.detected_footnotes,
        )
