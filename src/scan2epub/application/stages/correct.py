"""The post-correction stage and its guardrail.

The corrector is the only component that may change the words of a book, so
the stage that applies it is the one that decides whether the change is
acceptable.

Two limits are enforced, and they are enforced **locally**, on the result
and not on the trust in the model:

* the **normalised edit distance** between the original and the correction
  must not exceed ``max_distance``;
* the **relative change of the length** must not exceed ``max_length_change``.

A correction that breaks one of them is thrown away and the original text is
kept. The diff is recorded either way, so the user can review what the model
tried to do.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scan2epub.application.stages.clean import CleanResult
from scan2epub.config import CleanConfig
from scan2epub.domain.distance import levenshtein_bounded
from scan2epub.domain.models import CorrectionResult, DiffEntry, PageContent, TextBlock
from scan2epub.domain.ports import TextCorrector
from scan2epub.logging import get_logger

__all__ = ["CorrectionOutcome", "apply_corrector", "measure"]

_LOGGER = get_logger(__name__)


def _empty_notes() -> list[str]:
    """Return an empty list of notes."""
    return []


@dataclass(frozen=True, slots=True)
class CorrectionOutcome:
    """The outcome of a correction pass."""

    pages: tuple[PageContent, ...] = ()
    entries: tuple[DiffEntry, ...] = ()
    accepted: int = 0
    rejected: int = 0
    notes: list[str] = field(default_factory=_empty_notes)

    @property
    def changed(self) -> int:
        """The number of blocks that were really changed."""
        return sum(1 for entry in self.entries if entry.original != entry.corrected)


def measure(original: str, corrected: str, *, max_distance: float) -> float:
    """Return the normalised edit distance between two texts.

    The distance is computed with the banded Levenshtein algorithm, so it
    stays fast on long paragraphs: the computation stops as soon as the
    distance is known to be above the limit.

    Args:
        original: The text that was recognised.
        corrected: The text that the model proposes.
        max_distance: The limit above which the distance is not computed
            exactly.

    Returns:
        The distance, between `0.0` and `1.0`. It is capped at
        ``max_distance + 1`` when it is above the limit.
    """
    if original == corrected:
        return 0.0
    longest = max(len(original), len(corrected))
    if longest == 0:
        return 0.0
    limit = max(1, int(max_distance * longest) + 1)
    distance = levenshtein_bounded(original, corrected, limit)
    return min(1.0, distance / longest)


def _length_change(original: str, corrected: str) -> float:
    """Return the relative change of the length of a text."""
    if not original:
        return 0.0 if not corrected else 1.0
    return abs(len(corrected) - len(original)) / len(original)


def _accept(entry: DiffEntry, config: CleanConfig) -> tuple[bool, str | None]:
    """Decide whether a correction is acceptable."""
    if entry.original == entry.corrected:
        return True, None
    if entry.distance > config.max_correction_distance:
        return False, (
            f"the correction is too far from the original "
            f"({entry.distance:.3f} > {config.max_correction_distance:.3f})"
        )
    change = _length_change(entry.original, entry.corrected)
    if change > config.max_correction_length_change:
        return False, (
            f"the correction changed the length by {change:.1%} "
            f"(the limit is {config.max_correction_length_change:.1%})"
        )
    return True, None


def apply_corrector(
    pages: list[PageContent],
    corrector: TextCorrector,
    config: CleanConfig | None = None,
) -> CorrectionOutcome:
    """Correct the text of every page, and keep only the safe corrections.

    Args:
        pages: The cleaned pages.
        corrector: The corrector to apply.
        config: The limits of the guardrail.

    Returns:
        The outcome of the pass: the corrected pages and the diffs.
    """
    settings = config or CleanConfig()
    output: list[PageContent] = []
    entries: list[DiffEntry] = []
    accepted = 0
    rejected = 0

    for page in pages:
        result: CorrectionResult = corrector.correct(page.blocks)
        blocks: list[TextBlock] = []
        for index, original in enumerate(page.blocks):
            entry = result.entries[index] if index < len(result.entries) else None
            if entry is None:
                blocks.append(original)
                continue
            ok, reason = _accept(entry, settings)
            if ok:
                accepted += 1
                blocks.append(
                    original.with_text(entry.corrected)
                    if entry.corrected != original.text
                    else original
                )
                entries.append(entry)
            else:
                rejected += 1
                blocks.append(original)
                entries.append(
                    DiffEntry(
                        page=entry.page,
                        order=entry.order,
                        original=entry.original,
                        corrected=entry.corrected,
                        distance=entry.distance,
                        accepted=False,
                        reason=reason,
                    )
                )
        output.append(PageContent(index=page.index, blocks=tuple(blocks)))

    notes: list[str] = []
    if rejected:
        notes.append(f"{rejected} corrections were rejected by the guardrail")
        _LOGGER.info("correction.rejected", count=rejected)
    return CorrectionOutcome(
        pages=tuple(output),
        entries=tuple(entries),
        accepted=accepted,
        rejected=rejected,
        notes=notes,
    )


def to_clean_result(result: CleanResult, outcome: CorrectionOutcome) -> CleanResult:
    """Return the clean result with the corrections applied."""
    return CleanResult(
        pages=outcome.pages,
        removed_running_heads=result.removed_running_heads,
        removed_page_numbers=result.removed_page_numbers,
        joined_hyphens=result.joined_hyphens,
        merged_paragraphs=result.merged_paragraphs,
        detected_footnotes=result.detected_footnotes,
    )
