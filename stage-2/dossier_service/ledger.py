"""Budget accounting for one build: at most BUILD_BUDGET_UNITS, every unit counted."""
from __future__ import annotations

import threading
from collections.abc import Callable


class BudgetExhausted(Exception):
    """The next call would take the build over its budget."""


class Ledger:
    """Reserve units before a call, then settle: keep them (the call cost) or release them (it was refused).

    ``spent`` counts settled and in-flight units alike, so concurrent calls can never
    jointly exceed the cap. ``on_settled`` receives the units a settled call really cost.
    """

    def __init__(self, cap: int, on_settled: Callable[[int], None]) -> None:
        self._cap = cap
        self._on_settled = on_settled
        self._lock = threading.Lock()
        self.spent = 0

    def reserve(self, cost: int) -> None:
        with self._lock:
            if self.spent + cost > self._cap:
                raise BudgetExhausted()
            self.spent += cost

    def settle(self, cost: int, charged: bool) -> None:
        if charged:
            self._on_settled(cost)
            return
        with self._lock:
            self.spent -= cost

    def remaining(self) -> int:
        with self._lock:
            return self._cap - self.spent
