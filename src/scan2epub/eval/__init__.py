"""The evaluation of the OCR engines."""

from __future__ import annotations

from scan2epub.eval.metrics import (
    character_error_rate,
    normalise,
    word_error_rate,
    word_tokens,
)
from scan2epub.eval.runner import (
    SampleResult,
    evaluate_sample,
    render_markdown,
    sample_directories,
)

__all__ = [
    "SampleResult",
    "character_error_rate",
    "evaluate_sample",
    "normalise",
    "render_markdown",
    "sample_directories",
    "word_error_rate",
    "word_tokens",
]
