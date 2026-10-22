"""Tests of the cost estimate and of the budget."""

from __future__ import annotations

import pytest

from scan2epub.application.budget import Budget
from scan2epub.errors import BudgetExceededError
from scan2epub.infrastructure.llm.cost import (
    CostEstimate,
    estimate_cost,
    estimate_tokens,
    model_price,
    price_table,
)


def test_an_empty_text_costs_no_token() -> None:
    """An empty text has no token."""
    assert estimate_tokens("") == 0


def test_the_estimate_is_generous() -> None:
    """The estimate is an upper bound, never an average."""
    text = "palabra " * 100
    assert estimate_tokens(text) >= len(text) / 4


def test_the_price_table_is_not_empty() -> None:
    """There is always a price table."""
    assert price_table()


def test_a_known_model_has_a_price() -> None:
    """The models of the fallback table have a price."""
    price = model_price("gpt-4o-mini")
    assert price is not None
    assert price[0] > 0


def test_the_provider_prefix_is_ignored() -> None:
    """``openai/gpt-4o-mini`` and ``gpt-4o-mini`` cost the same."""
    assert model_price("openai/gpt-4o-mini") == model_price("gpt-4o-mini")


def test_an_unknown_model_has_no_price() -> None:
    """An unknown model is reported."""
    assert model_price("a-model-that-does-not-exist") is None


def test_the_cost_of_a_call_is_computed() -> None:
    """The cost of a call is the price of the tokens."""
    input_cost, output_cost, note = estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert note is None
    assert input_cost > 0
    assert output_cost > input_cost


def test_an_unknown_model_costs_nothing_and_says_so() -> None:
    """The estimate of an unknown model is honest about it."""
    input_cost, output_cost, note = estimate_cost("nope", 1000, 1000)
    assert input_cost == 0.0
    assert output_cost == 0.0
    assert note is not None


def test_the_estimate_renders_a_report() -> None:
    """The estimate can be printed."""
    estimate = CostEstimate(
        input_tokens=1000,
        output_tokens=500,
        input_cost=0.001,
        output_cost=0.002,
        models={"gpt-4o-mini": 0.003},
        notes=["a note"],
    )
    report = estimate.render()
    assert "TOTAL" in report
    assert "$0.0030" in report
    assert "a note" in report


def test_a_budget_without_a_limit_lets_everything_through() -> None:
    """A run without a budget is not stopped."""
    budget = Budget()
    budget.check(1000.0)
    budget.charge(1000.0)
    assert budget.spent == 1000.0
    assert budget.remaining is None


def test_a_budget_stops_a_call_that_goes_over() -> None:
    """The budget is a wall, not a report."""
    budget = Budget(limit=1.0)
    budget.charge(0.5)
    with pytest.raises(BudgetExceededError):
        budget.check(0.75)


def test_a_budget_stops_a_call_that_already_went_over() -> None:
    """The budget is checked when the call is charged."""
    budget = Budget(limit=1.0)
    with pytest.raises(BudgetExceededError):
        budget.charge(1.5)


def test_the_remaining_budget_is_reported() -> None:
    """What is left of the budget is known."""
    budget = Budget(limit=2.0)
    budget.charge(0.5)
    assert budget.remaining == pytest.approx(1.5)
