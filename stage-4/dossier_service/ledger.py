"""Budget accounting for one build: the units it may still spend, and every unit counted.

A build spends at most ``BUILD_BUDGET_UNITS``, and a build of a batch also draws on the batch's shared
budget. The store keeps the counts (it journals them, so they survive a restart) and answers for them.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


class BudgetExhausted(Exception):
    """The next call would take the build, or its batch, over budget."""


@dataclass(frozen=True)
class Ledger:
    """Reserve units before a call, then settle: keep them (the call cost) or release them (it was refused).

    A reserved unit counts as spent for every cap, so concurrent calls can never jointly exceed one.
    """
    reserve: Callable[[int], None]          # raises BudgetExhausted
    settle: Callable[[int, bool], None]     # the units reserved, and whether the call really cost them
    remaining: Callable[[], int]            # units the build may still reserve
