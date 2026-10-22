"""The budget of a run.

The limit is enforced **locally**: the run stops when the budget is
reached. It is not a report that the user has to read, it is a wall.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scan2epub.errors import BudgetExceededError
from scan2epub.logging import get_logger

__all__ = ["Budget", "BudgetExceededError"]

_LOGGER = get_logger(__name__)


def _empty_notes() -> list[str]:
    """Return an empty list of notes."""
    return []


@dataclass
class Budget:
    """The budget of a run, in US dollars."""

    limit: float | None = None
    spent: float = 0.0
    calls: int = 0
    notes: list[str] = field(default_factory=_empty_notes)

    @property
    def remaining(self) -> float | None:
        """Return what is left of the budget, or ``None`` when there is none."""
        if self.limit is None:
            return None
        return max(0.0, self.limit - self.spent)

    def check(self, estimated_cost: float) -> None:
        """Refuse a call that would go over the budget.

        Args:
            estimated_cost: The estimated cost of the call.

        Raises:
            BudgetExceededError: If the call would exceed the limit.
        """
        if self.limit is None:
            return
        if self.spent + estimated_cost > self.limit:
            raise BudgetExceededError(
                f"The call would cost ${estimated_cost:.4f}, which goes over the "
                f"budget: ${self.spent:.4f} of ${self.limit:.4f} is already spent. "
                "Raise `max_cost_usd` in the configuration, or use a cheaper model."
            )

    def charge(self, cost: float) -> None:
        """Record the cost of a call that has been made.

        Args:
            cost: The cost of the call.

        Raises:
            BudgetExceededError: If the budget is now exceeded.
        """
        self.spent += cost
        self.calls += 1
        if self.limit is not None and self.spent > self.limit:
            raise BudgetExceededError(
                f"The run cost ${self.spent:.4f}, which is over the budget of "
                f"${self.limit:.4f}. Raise `max_cost_usd` in the configuration."
            )
        _LOGGER.debug("budget.charged", cost=cost, spent=self.spent, calls=self.calls)
