"""PaddleOCR-VL adapter.

PaddleOCR-VL is a vision-language model that reads a scanned page and writes
its text as Markdown. The Markdown keeps the structure of the page: the
paragraphs, the headings and the lists. The adapter turns that Markdown into
the text blocks of the domain.

The weights are **not** committed to the repository: they are downloaded on
demand from the model hub the first time a page is read.
"""

# PyTorch and Transformers are optional dependencies of the project: they live
# in the `vlm` extra and they are imported lazily, inside `_load()`, so that
# importing this module never pulls in PyTorch. Their types are unknown when
# the extra is not installed, so they are not type checked.
# pyright: reportMissingImports=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownParameterType=false

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from PIL import Image

from scan2epub.domain.models import BBox, BlockKind, PageImage, TextBlock
from scan2epub.errors import EngineNotAvailableError, OcrError

__all__ = ["PaddleOcrVlEngine"]

#: The prompt that asks the model for the text of the page.
_PROMPT = "OCR:"

#: The margin of the text area, in normalised units.
_MARGIN = 0.05

#: The Markdown image, which carries no text to read.
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

#: The Markdown link, which keeps only its label.
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")

#: The HTML tag, which carries no text to read.
_TAG_RE = re.compile(r"<[^>]+>")

#: The emphasis of a word, which carries no text to read.
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|~~|`)(?=\S)(.+?)(?<=\S)\1")

#: The list item, which starts a new block of text.
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

#: The horizontal rule, which is not text.
_RULE_RE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")

#: The Markdown heading, which carries its level.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass(frozen=True, slots=True)
class _Paragraph:
    """A paragraph of the Markdown, with the level of its heading."""

    lines: tuple[str, ...]
    level: int = 0


def _clean(text: str) -> str:
    """Remove the Markdown markup of a line of text.

    Args:
        text: The line of Markdown.

    Returns:
        The line of plain text.
    """
    cleaned = _IMAGE_RE.sub("", text)
    cleaned = _LINK_RE.sub(r"\1", cleaned)
    cleaned = _TAG_RE.sub("", cleaned)
    cleaned = _EMPHASIS_RE.sub(r"\2", cleaned)
    return cleaned.strip()


def _parse_markdown(markdown: str) -> list[_Paragraph]:
    """Convert the Markdown of the model into paragraphs of plain text.

    A paragraph is a run of lines that are not separated by a blank line. The
    physical lines of the paragraph are kept, because the cleaner repairs the
    hyphenation with them.

    Args:
        markdown: The Markdown that the model wrote.

    Returns:
        The paragraphs of the page, in reading order.
    """
    paragraphs: list[_Paragraph] = []
    lines: list[str] = []
    level = 0

    def flush() -> None:
        """Close the paragraph that is being read."""
        nonlocal level, lines
        text = tuple(line for line in lines if line)
        if text:
            paragraphs.append(_Paragraph(lines=text, level=level))
        lines = []
        level = 0

    for raw in markdown.splitlines():
        stripped = raw.strip()
        if not stripped:
            flush()
            continue
        if _RULE_RE.match(stripped):
            flush()
            continue
        heading = _HEADING_RE.match(stripped)
        if heading is not None:
            flush()
            lines = [_clean(heading.group(2))]
            level = len(heading.group(1))
            continue
        if _LIST_RE.match(stripped):
            flush()
            lines = [_clean(_LIST_RE.sub("", stripped, count=1))]
            continue
        cleaned = _clean(stripped)
        if cleaned:
            lines.append(cleaned)
    flush()
    return paragraphs


class PaddleOcrVlEngine:
    """Recognise pages with PaddleOCR-VL.

    Attributes:
        name: The engine identifier used in the configuration file.
    """

    name = "paddleocr-vl"

    def __init__(
        self,
        *,
        model: str = "PaddlePaddle/PaddleOCR-VL",
        device: str = "auto",
        max_new_tokens: int = 4096,
        revision: str | None = None,
        trust_remote_code: bool = False,
    ) -> None:
        """Initialise the engine.

        The model is loaded the first time a page is read, so that building
        the engine stays cheap.

        Args:
            model: The identifier of the model on the model hub.
            device: The device the model runs on. ``"auto"`` picks the GPU
                when the machine has one, and the CPU otherwise.
            max_new_tokens: The maximum number of tokens the model may
                generate for one page.
            revision: The revision of the model to load. ``None`` loads the
                default revision of the repository.
            trust_remote_code: Whether the code of the model repository may
                run. Leave it off unless the repository is trusted.
        """
        self.model = model
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.revision = revision
        self.trust_remote_code = trust_remote_code
        self._processor: Any | None = None
        self._model: Any | None = None

    def describe(self) -> dict[str, object]:
        """Return the settings that change the result of the recognition."""
        return {
            "engine": self.name,
            "model": self.model,
            "device": self.device,
            "max_new_tokens": self.max_new_tokens,
            "revision": self.revision,
        }

    def recognize(self, image: PageImage) -> list[TextBlock]:
        """Recognise the text of a page.

        Args:
            image: The page to read.

        Returns:
            The text blocks of the page, in reading order. Every block keeps
            its physical lines so that the cleaner can repair hyphenation.

        Raises:
            EngineNotAvailableError: If the model cannot be loaded.
            OcrError: If the page cannot be read or the model fails.
        """
        markdown = self._transcribe(image)
        return self._layout(_parse_markdown(markdown), image)

    def _load(self) -> tuple[Any, Any]:
        """Load the processor and the model, downloading the weights.

        Returns:
            The processor and the model.

        Raises:
            EngineNotAvailableError: If PyTorch, Transformers or the weights
                of the model are not available.
        """
        if self._processor is not None and self._model is not None:
            return self._processor, self._model
        try:
            import torch  # noqa: PLC0415 - the import must stay lazy
            from transformers import AutoModel, AutoProcessor  # noqa: PLC0415 - lazy import
        except ImportError as exc:
            raise EngineNotAvailableError(self._install_message()) from exc
        try:
            processor = AutoProcessor.from_pretrained(
                self.model,
                revision=self.revision,
                trust_remote_code=self.trust_remote_code,
            )
            model = AutoModel.from_pretrained(
                self.model,
                revision=self.revision,
                trust_remote_code=self.trust_remote_code,
            )
        except Exception as exc:
            raise EngineNotAvailableError(self._load_message()) from exc
        model = model.to(self._resolve_device(torch))
        model.eval()
        self._processor = processor
        self._model = model
        return processor, model

    def _resolve_device(self, torch: Any) -> str:  # noqa: ANN401 - torch has no stubs
        """Return the device the model runs on.

        Args:
            torch: The PyTorch module.

        Returns:
            The name of the device.
        """
        if self.device != "auto":
            return self.device
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def _install_message(self) -> str:
        """Return the message that explains how to install the engine."""
        return (
            "PaddleOCR-VL is not available. Install the vision-language extra with "
            "'pip install scan2epub[vlm]', which brings PyTorch and Transformers, or "
            "install them directly with 'pip install torch transformers'. The weights "
            f"of {self.model} are downloaded on demand the first time a page is read, "
            "and they are never committed to the repository."
        )

    def _load_message(self) -> str:
        """Return the message that explains why the model did not load."""
        return (
            f"The model {self.model} could not be loaded. Install the vision-language "
            "extra with 'pip install scan2epub[vlm]' and check the network connection: "
            "the weights are downloaded on demand from the model hub, and they are not "
            "part of the repository."
        )

    def _transcribe(self, image: PageImage) -> str:
        """Return the Markdown that the model wrote for the page.

        Args:
            image: The page to read.

        Returns:
            The Markdown of the page.

        Raises:
            OcrError: If the page cannot be read or the model fails.
        """
        processor, model = self._load()
        try:
            with Image.open(image.path) as page:
                inputs = self._prepare_inputs(processor, page)
        except OSError as exc:
            raise OcrError(f"The page {image.index + 1} cannot be read: {exc}") from exc
        try:
            generated = model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        except Exception as exc:
            raise OcrError(f"PaddleOCR-VL failed on the page {image.index + 1}: {exc}") from exc
        return self._decode(processor, generated, inputs)

    def _prepare_inputs(
        self,
        processor: Any,  # noqa: ANN401 - transformers has no stubs
        page: Image.Image,
    ) -> dict[str, Any]:
        """Build the tensors that the model reads.

        Args:
            processor: The processor of the model.
            page: The page to read.

        Returns:
            The tensors, ready for the model.
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": page},
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ]
        template = getattr(processor, "apply_chat_template", None)
        if template is not None:
            inputs = template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            )
        else:
            inputs = processor(text=_PROMPT, images=page, return_tensors="pt")
        return dict(inputs)

    def _decode(
        self,
        processor: Any,  # noqa: ANN401 - transformers has no stubs
        generated: Any,  # noqa: ANN401 - the tensors have no stubs
        inputs: dict[str, Any],
    ) -> str:
        """Return the text that the model generated.

        The prompt is cut away, so that only the text of the page is left.

        Args:
            processor: The processor of the model.
            generated: The tokens that the model generated.
            inputs: The tensors that the model read.

        Returns:
            The text of the page.
        """
        prompt_length = 0
        input_ids = inputs.get("input_ids")
        if input_ids is not None:
            prompt_length = int(input_ids.shape[-1])
        sequences = generated[:, prompt_length:] if prompt_length else generated
        return str(processor.batch_decode(sequences, skip_special_tokens=True)[0])

    def _layout(self, paragraphs: list[_Paragraph], image: PageImage) -> list[TextBlock]:
        """Place the paragraphs of the page on the page.

        The Markdown of the model carries no coordinates, so the blocks are
        laid out from the top of the page to the bottom, in proportion to the
        number of lines of every paragraph.

        Args:
            paragraphs: The paragraphs of the page.
            image: The page that was read.

        Returns:
            The text blocks of the page, in reading order.
        """
        total = sum(len(paragraph.lines) for paragraph in paragraphs)
        if total == 0:
            return []
        blocks: list[TextBlock] = []
        consumed = 0
        for paragraph in paragraphs:
            count = len(paragraph.lines)
            y0 = _MARGIN + (1.0 - 2.0 * _MARGIN) * consumed / total
            y1 = _MARGIN + (1.0 - 2.0 * _MARGIN) * (consumed + count) / total
            consumed += count
            blocks.append(
                TextBlock(
                    lines=paragraph.lines,
                    bbox=BBox(_MARGIN, y0, 1.0 - _MARGIN, y1),
                    confidence=1.0,
                    kind=BlockKind.HEADING if paragraph.level else BlockKind.BODY,
                    order=len(blocks),
                    page=image.index,
                    level=paragraph.level,
                )
            )
        return blocks
