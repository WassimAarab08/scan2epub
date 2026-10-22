"""The LLM text corrector, on top of LiteLLM.

The corrector is the only component that may change the words of a book, so
it is fenced in. The prompt forbids the rewriting, and the application layer
measures the distance between the original and the correction and throws the
correction away when it drifts too far.

The API keys are read from the environment by LiteLLM itself. They are never
written to the configuration file and never logged.
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Callable, Sequence
from importlib import import_module
from typing import cast

from scan2epub.domain.models import CorrectionResult, DiffEntry, TextBlock
from scan2epub.errors import EngineNotAvailableError

__all__ = ["CORRECTION_PROMPT", "LiteLlmCorrector"]

#: The prompt of the corrector. It is deliberately narrow: the model may only
#: repair the recognition errors.
CORRECTION_PROMPT = """\
You are a proofreading engine for scanned historical books.

You receive the text of one page of a book printed before 1900. The text was
recognised by an OCR engine and it may contain recognition errors.

Rules, in this order:
1. Fix ONLY the recognition errors: characters that were misread, missing or
   added by the scanner.
2. Do NOT rewrite, summarise, translate, modernise or reformat the text.
3. Do NOT change the spelling, the grammar, the punctuation or the capital
   letters of the original.
4. Do NOT add or remove any word.
5. Keep the line breaks of the text as they are.

Answer with the corrected text and nothing else. If the text has no error,
answer with exactly the same text.
"""


class LiteLlmCorrector:
    """Repair the OCR mistakes with a language model."""

    name = "litellm"

    def __init__(
        self,
        model: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout: float = 120.0,
        api_base: str | None = None,
    ) -> None:
        """Initialise the corrector.

        Args:
            model: The model, with the prefix of the provider
                (``openai/gpt-4o-mini``, ``ollama/qwen3``…).
            temperature: The temperature of the requests. Zero by default, so
                that the correction is reproducible.
            max_tokens: The maximum number of tokens of the answer.
            timeout: The timeout of a request, in seconds.
            api_base: The address of a local server, for the providers that
                need it.
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.api_base = api_base

    def describe(self) -> dict[str, object]:
        """Return the settings that change the result."""
        return {
            "engine": self.name,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    def correct(self, blocks: Sequence[TextBlock]) -> CorrectionResult:
        """Return the corrected blocks and the diffs.

        Args:
            blocks: The blocks of one page.

        Returns:
            The corrected blocks and the diffs of the corrector.

        Raises:
            EngineNotAvailableError: If LiteLLM is not installed.
        """
        if not blocks:
            return CorrectionResult(blocks=(), entries=())
        original = "\n".join(block.text for block in blocks)
        answer = self._ask(original)
        corrected = answer.split("\n")
        entries: list[DiffEntry] = []
        output: list[TextBlock] = []
        for index, block in enumerate(blocks):
            text = corrected[index] if index < len(corrected) else block.text
            output.append(block.with_text(text))
            entries.append(
                DiffEntry(
                    page=block.page,
                    order=block.order,
                    original=block.text,
                    corrected=text,
                    distance=distance_between(block.text, text),
                    accepted=True,
                )
            )
        return CorrectionResult(blocks=tuple(output), entries=tuple(entries))

    def _ask(self, text: str) -> str:
        """Send the text to the model and return its answer."""
        try:
            litellm = import_module("litellm")
        except ImportError as exc:  # pragma: no cover - depends on the machine
            raise EngineNotAvailableError(
                "LiteLLM is not installed. Run `uv sync --extra llm` to use the text corrector."
            ) from exc

        payload = [
            {"role": "system", "content": CORRECTION_PROMPT},
            {"role": "user", "content": text},
        ]
        try:
            completion = cast(Callable[..., object], litellm.completion)
            response = completion(
                model=self.model,
                messages=payload,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
                api_base=self.api_base,
            )
        except Exception as exc:
            raise EngineNotAvailableError(
                f"The model {self.model} could not be reached: {exc}"
            ) from exc
        return _extract_answer(response)


def _extract_answer(response: object) -> str:
    """Return the text of the answer of the model."""
    choices = _get(response, "choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = cast("list[object]", choices)[0]
    message = _get(first, "message")
    if message is None:
        return ""
    content = _get(message, "content")
    if isinstance(content, list):
        # Some providers answer with a list of parts.
        parts = cast("list[object]", content)
        pieces: list[str] = []
        for part in parts:
            if isinstance(part, dict):
                entry = cast("dict[str, object]", part)
                pieces.append(str(entry.get("text", "")))
            else:
                pieces.append(str(part))
        return "".join(pieces)
    if content is None:
        return ""
    return str(content)


def _get(container: object, name: str) -> object | None:
    """Return an attribute of an object, or a key of a mapping."""
    if isinstance(container, dict):
        entry = cast("dict[str, object]", container)
        return entry.get(name)
    return getattr(container, name, None)


def distance_between(original: str, corrected: str) -> float:
    """Return the normalised distance between two texts, between 0 and 1."""
    if original == corrected:
        return 0.0
    longest = max(len(original), len(corrected))
    if longest == 0:
        return 0.0
    matcher = difflib.SequenceMatcher(None, original, corrected)
    return 1.0 - matcher.ratio()


def dumps(payload: object) -> str:
    """Return a readable representation of a payload, for the logs."""
    return json.dumps(payload, ensure_ascii=False, default=str)
