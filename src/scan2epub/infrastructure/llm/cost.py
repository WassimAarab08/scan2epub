"""The estimation of the cost of a run.

Before a job spends money, the user has to know what it will cost. The
estimate is an **upper bound**: it assumes that every page costs the most it
can cost, never the average.

The prices come from the catalogue of LiteLLM, so they are never hard-coded
here. When LiteLLM is not installed, a small fallback table keeps the
estimate usable for the common models.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import cast

__all__ = [
    "CostEstimate",
    "estimate_cost",
    "estimate_tokens",
    "model_price",
    "price_table",
]

#: The number of characters that a token usually holds, for the languages
#: that use the Latin alphabet.
CHARS_PER_TOKEN = 4

#: The price of a million tokens, in US dollars, for the models that are not
#: in the catalogue of LiteLLM. The values are the cheapest tier.
FALLBACK_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-7-sonnet": (3.00, 15.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "mistral-small": (0.20, 0.60),
    "llama-3.1-8b": (0.05, 0.08),
    "qwen3": (0.00, 0.00),
}


def _empty_models() -> dict[str, float]:
    """Return an empty table of the cost of the models."""
    return {}


def _empty_notes() -> list[str]:
    """Return an empty list of notes."""
    return []


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """The estimated cost of a run."""

    input_tokens: int = 0
    output_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    models: dict[str, float] = field(default_factory=_empty_models)
    notes: list[str] = field(default_factory=_empty_notes)

    @property
    def total(self) -> float:
        """The total cost of the run, in US dollars."""
        return self.input_cost + self.output_cost

    def render(self) -> str:
        """Return the estimate as a readable report."""
        lines = [
            f"  input tokens   {self.input_tokens:,}",
            f"  output tokens  {self.output_tokens:,}",
            f"  input cost     ${self.input_cost:.4f}",
            f"  output cost    ${self.output_cost:.4f}",
            f"  TOTAL          ${self.total:.4f}",
        ]
        for model, cost in sorted(self.models.items()):
            lines.append(f"    - {model}: ${cost:.4f}")
        for note in self.notes:
            lines.append(f"  note: {note}")
        return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """Return the number of tokens of a text.

    The estimate is deliberately generous: it is an upper bound, not the
    exact count.

    Args:
        text: The text to measure.

    Returns:
        The number of tokens.
    """
    if not text:
        return 0
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def _litellm_catalogue() -> dict[str, object] | None:
    """Return the catalogue of the prices of LiteLLM, when it is installed.

    The import is dynamic because LiteLLM is an optional dependency: the
    estimate must work without it.
    """
    try:
        litellm = import_module("litellm")
    except ImportError:
        return None
    catalogue = getattr(litellm, "model_cost", None)
    if not isinstance(catalogue, dict):
        return None
    return cast("dict[str, object]", catalogue)


@lru_cache(maxsize=1)
def price_table() -> dict[str, tuple[float, float]]:
    """Return the prices of the models, in US dollars per million tokens.

    The catalogue of LiteLLM is used when it is installed; otherwise the
    fallback table is returned.
    """
    catalogue = _litellm_catalogue()
    if catalogue is None:
        return dict(FALLBACK_PRICES)

    prices: dict[str, tuple[float, float]] = {}
    for name, entry in catalogue.items():
        if not isinstance(entry, dict):
            continue
        data = cast("dict[str, object]", entry)
        input_price = data.get("input_cost_per_token")
        output_price = data.get("output_cost_per_token")
        if isinstance(input_price, int | float) and isinstance(output_price, int | float):
            prices[str(name)] = (float(input_price) * 1_000_000, float(output_price) * 1_000_000)
    return prices or dict(FALLBACK_PRICES)


def model_price(model: str) -> tuple[float, float] | None:
    """Return the price of a model, per million tokens.

    Args:
        model: The name of the model, with or without its provider prefix.

    Returns:
        The price of the input and of the output, or ``None`` when the model
        is not in the catalogue.
    """
    table = price_table()
    for candidate in (model, model.rsplit("/", 1)[-1]):
        if candidate in table:
            return table[candidate]
    return None


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> tuple[float, float, str | None]:
    """Estimate the cost of a call.

    Args:
        model: The name of the model.
        input_tokens: The number of tokens of the request.
        output_tokens: The number of tokens of the answer.

    Returns:
        The cost of the input, the cost of the output and a note when the
        model is not in the catalogue.
    """
    price = model_price(model)
    if price is None:
        return 0.0, 0.0, f"the price of {model} is unknown; the cost is not estimated"
    input_price, output_price = price
    return (
        input_tokens * input_price / 1_000_000,
        output_tokens * output_price / 1_000_000,
        None,
    )


def dump_prices(path: Path) -> None:
    """Write the price table to a file, for the documentation."""
    path.write_text(json.dumps(price_table(), indent=2, sort_keys=True), encoding="utf-8")
