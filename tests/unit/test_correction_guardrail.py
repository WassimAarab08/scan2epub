"""Tests of the guardrail of the text corrector.

The guardrail is the most important piece of the correction: the model is
never trusted, and a correction that drifts too far from the original is
thrown away.
"""

from __future__ import annotations

from scan2epub.application.stages.correct import apply_corrector, measure, to_clean_result
from scan2epub.config import CleanConfig
from scan2epub.domain.models import (
    BBox,
    CorrectionResult,
    DiffEntry,
    PageContent,
    TextBlock,
)
from scan2epub.domain.ports import TextCorrector


class _FakeCorrector:
    """A corrector that changes the text in a predictable way."""

    name = "fake"

    def __init__(self, replacement: str) -> None:
        self.replacement = replacement
        self.calls = 0

    def correct(self, blocks: list[TextBlock]) -> CorrectionResult:
        """Return the blocks with their text replaced."""
        self.calls += 1
        entries = []
        output = []
        for block in blocks:
            text = self.replacement
            entries.append(
                DiffEntry(
                    page=block.page,
                    order=block.order,
                    original=block.text,
                    corrected=text,
                    distance=measure(block.text, text, max_distance=1.0),
                    accepted=True,
                )
            )
            output.append(block.with_text(text))
        return CorrectionResult(blocks=tuple(output), entries=tuple(entries))


def _page(text: str = "El hombre que escribe con la letra larga.") -> PageContent:
    """Return a page with one block."""
    block = TextBlock(lines=(text,), bbox=BBox(0.1, 0.2, 0.9, 0.3))
    return PageContent(index=0, blocks=(block,))


def test_the_distance_of_two_identical_texts_is_zero() -> None:
    """The same text has no distance."""
    assert measure("hola", "hola", max_distance=0.12) == 0.0


def test_the_distance_grows_with_the_change() -> None:
    """A bigger change means a bigger distance."""
    small = measure("el gato", "el gata", max_distance=1.0)
    big = measure("el gato", "el caballo", max_distance=1.0)
    assert small < big


def test_a_small_correction_is_accepted() -> None:
    """A correction of one character is accepted."""
    corrector = _FakeCorrector("El hombre que escribe con la letra larga.")
    outcome = apply_corrector([_page()], corrector, CleanConfig())
    assert outcome.accepted == 1
    assert outcome.rejected == 0
    assert outcome.pages[0].blocks[0].text == "El hombre que escribe con la letra larga."


def test_a_rewrite_is_rejected() -> None:
    """A correction that rewrites the text is thrown away."""
    corrector = _FakeCorrector("Una historia completamente distinta, escrita de nuevo.")
    outcome = apply_corrector([_page()], corrector, CleanConfig())
    assert outcome.rejected == 1
    assert outcome.accepted == 0
    # The original text is kept.
    assert outcome.pages[0].blocks[0].text == "El hombre que escribe con la letra larga."


def test_the_rejected_correction_is_still_recorded() -> None:
    """The user can see what the model tried to do."""
    corrector = _FakeCorrector("Otra cosa enteramente distinta.")
    outcome = apply_corrector([_page()], corrector, CleanConfig())
    assert len(outcome.entries) == 1
    assert outcome.entries[0].accepted is False
    assert outcome.entries[0].reason is not None
    assert outcome.entries[0].corrected == "Otra cosa enteramente distinta."


def test_a_change_of_the_length_is_rejected() -> None:
    """A correction that changes the length too much is thrown away."""
    corrector = _FakeCorrector("El.")
    outcome = apply_corrector([_page()], corrector, CleanConfig())
    assert outcome.rejected == 1
    assert outcome.pages[0].blocks[0].text.startswith("El hombre")


def test_the_limits_are_configurable() -> None:
    """A stricter configuration rejects more."""
    original = "El hombre que escribe con la letra larga."
    corrector = _FakeCorrector("El hombre que escribe con la letra larga,")
    # The distance is above zero, so a limit of zero rejects it.
    strict = CleanConfig(max_correction_distance=0.0, max_correction_length_change=1.0)
    outcome = apply_corrector([_page(original)], corrector, strict)
    assert outcome.rejected == 1
    # The same correction is accepted with the default limits.
    lenient = apply_corrector([_page(original)], corrector, CleanConfig())
    assert lenient.accepted == 1


def test_a_corrector_without_entries_keeps_the_text() -> None:
    """A corrector that answers nothing does not break the book."""

    class _Silent(TextCorrector):
        """A corrector that never answers."""

        name = "silent"

        def correct(self, blocks: list[TextBlock]) -> CorrectionResult:
            """Return the blocks unchanged."""
            return CorrectionResult(blocks=tuple(blocks), entries=())

    outcome = apply_corrector([_page()], _Silent(), CleanConfig())
    assert outcome.pages[0].blocks[0].text.startswith("El hombre")
    assert outcome.entries == ()


def test_the_clean_result_keeps_the_counters() -> None:
    """The summary of the cleaning survives the correction."""
    from scan2epub.application.stages.clean import clean_pages

    cleaned = clean_pages([_page()], CleanConfig())
    corrector = _FakeCorrector("El hombre que escribe con la letra larga.")
    outcome = apply_corrector(list(cleaned.pages), corrector, CleanConfig())
    result = to_clean_result(cleaned, outcome)
    assert result.removed_page_numbers == cleaned.removed_page_numbers
    assert result.merged_paragraphs == cleaned.merged_paragraphs
