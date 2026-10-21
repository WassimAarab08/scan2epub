# Adding an OCR engine or a text corrector

The engine and the corrector are **ports**: protocols with pluggable
adapters. Writing one takes less than fifty lines of code, and the
[architecture](architecture.md) explains why they are the way they are.

## The contract of an OCR engine

An engine receives a page image and returns the blocks of the page, in
reading order.

```python
from scan2epub.domain.models import BBox, BlockKind, PageImage, TextBlock


class MyEngine:
    """Recognises the text of a page with my own library."""

    name = "my-engine"

    def recognize(self, image: PageImage) -> list[TextBlock]:
        """Return the text blocks of the page."""
        raw = my_library.read(str(image.path))
        return [
            TextBlock(
                lines=tuple(block.text.split("\n")),
                bbox=BBox.from_pixels(
                    block.left,
                    block.top,
                    block.width,
                    block.height,
                    image.width,
                    image.height,
                ),
                confidence=block.score,
                kind=BlockKind.BODY,
                order=index,
                page=image.index,
            )
            for index, block in enumerate(raw)
        ]
```

That is the whole adapter. The rules:

| Rule | Why |
| --- | --- |
| Keep the physical lines | The cleaner repairs the hyphenation with them. |
| Normalise the coordinates | `BBox.from_pixels` does it for you. |
| Return the blocks in reading order | The structure stage relies on it. |
| Set `page=image.index` | The review view needs to know the page. |
| Do not rewrite the text | That is the corrector's job, and it is guarded. |

## The contract of a text corrector

A corrector receives the blocks of a page and returns the corrected blocks
**and** the diffs it produced.

```python
from scan2epub.domain.models import CorrectionResult, DiffEntry, TextBlock


class MyCorrector:
    """Repairs the OCR mistakes with my own model."""

    name = "my-corrector"

    def correct(self, blocks: list[TextBlock]) -> CorrectionResult:
        """Return the corrected blocks and the diffs."""
        corrected = []
        entries = []
        for block in blocks:
            fixed = my_model.repair(block.text)
            entries.append(
                DiffEntry(
                    page=block.page,
                    order=block.order,
                    original=block.text,
                    corrected=fixed,
                    distance=my_distance(block.text, fixed),
                    accepted=True,
                )
            )
            corrected.append(block.with_text(fixed))
        return CorrectionResult(blocks=tuple(corrected), entries=tuple(entries))
```

The corrector is **not** trusted. The application layer measures the distance
between the original and the correction and throws it away when it drifts too
far. That is why `DiffEntry` carries the distance: the guardrail needs it,
and the user needs the diffs to review what changed.

## Registering the adapter

Adapters are declared in `config.toml`:

```toml
[ocr.my-engine]
adapter = "my_package.my_module:MyEngine"

[ocr.my-engine.options]
model = "my-model"
device = "cpu"
```

```toml
[correct.my-corrector]
adapter = "my_package.my_module:MyCorrector"

[correct.my-corrector.options]
temperature = 0.0
```

The `adapter` is an import path in the form `module:Class`. The provider
registry imports it lazily, so an optional dependency is only needed when the
adapter is actually used.

Then use it:

```bash
scan2epub convert libro.pdf -o libro.epub --ocr my-engine
```

## A complete example

Here is a working adapter that uses the `difflib` module of the standard
library, in fewer than fifty lines:

```python
"""A text corrector that fixes the characters Tesseract confuses."""

from __future__ import annotations

import difflib

from scan2epub.domain.models import CorrectionResult, DiffEntry, TextBlock

#: The confusions that are typical of old Spanish books.
CONFUSIONS = {
    "rn": "m",
    "cl": "d",
    "l": "1",
}


class DifflibCorrector:
    """Repairs the OCR mistakes with a set of substitution rules."""

    name = "difflib"

    def __init__(self, *, max_distance: float = 0.12) -> None:
        """Initialise the corrector.

        Args:
            max_distance: The maximum normalised edit distance that a
                correction may reach before it is rejected.
        """
        self.max_distance = max_distance

    def correct(self, blocks: list[TextBlock]) -> CorrectionResult:
        """Return the corrected blocks and the diffs."""
        corrected: list[TextBlock] = []
        entries: list[DiffEntry] = []
        for block in blocks:
            fixed = self._repair(block.text)
            ratio = difflib.SequenceMatcher(None, block.text, fixed).ratio()
            distance = 1.0 - ratio
            entries.append(
                DiffEntry(
                    page=block.page,
                    order=block.order,
                    original=block.text,
                    corrected=fixed,
                    distance=distance,
                    accepted=distance <= self.max_distance,
                    reason=None if distance <= self.max_distance else "too far from the original",
                )
            )
            corrected.append(block.with_text(fixed))
        return CorrectionResult(blocks=tuple(corrected), entries=tuple(entries))

    def _repair(self, text: str) -> str:
        """Apply the substitution rules to a piece of text."""
        for wrong, right in CONFUSIONS.items():
            text = text.replace(wrong, right)
        return text
```

Register it:

```toml
[correct.difflib]
adapter = "my_package.difflib_corrector:DifflibCorrector"
```

## Testing the adapter

The test suite has helpers that make an adapter easy to check:

```python
from scan2epub.domain.models import BBox, PageImage, TextBlock


def test_my_engine_reads_the_page() -> None:
    """The engine returns the blocks of the page."""
    engine = MyEngine()
    page = PageImage(index=0, path=Path("page.png"), width=1000, height=1000)
    blocks = engine.recognize(page)
    assert blocks
    assert blocks[0].text
    assert 0.0 <= blocks[0].confidence <= 1.0
```

For the corrector, the important test is the guardrail: a corrector that
rewrites the text must be rejected.

```python
def test_the_corrector_does_not_rewrite() -> None:
    """A correction that drifts too far is rejected."""
    corrector = DifflibCorrector(max_distance=0.01)
    block = TextBlock.from_text("el comrpensor", BBox(0.1, 0.1, 0.9, 0.2))
    result = corrector.correct([block])
    assert result.entries[0].accepted is False
```

## Checklist before you open the pull request

- [ ] The adapter only imports the `domain` models, never another adapter.
- [ ] The engine returns the blocks in reading order, with the physical lines.
- [ ] The corrector returns the diffs together with the corrected blocks.
- [ ] The licence of the engine and of its model weights is permissive, and
      both are listed in [`THIRD_PARTY_LICENSES.md`](../THIRD_PARTY_LICENSES.md).
- [ ] The model weights are **not** committed: they are downloaded on demand.
- [ ] The adapter has tests.
- [ ] `uv run ruff check .`, `uv run pyright` and `uv run pytest` are green.
