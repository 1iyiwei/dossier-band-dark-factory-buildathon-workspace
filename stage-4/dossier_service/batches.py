"""A batch: several companies researched under one shared budget, by the user who created it."""
from __future__ import annotations

from dataclasses import dataclass, field

from .domains import is_valid_domain

MAX_BATCH_DOMAINS = 50
MIN_BUDGET, MAX_BUDGET = 1, 100_000


@dataclass
class Batch:
    batch_id: str
    user_id: str
    budget_units: int
    domains: list[str]                                  # normalised, in the order given
    builds: list[str] = field(default_factory=list)     # the domains whose first build this batch runs
    spent_units: int = 0                                # what the provider calls of its builds cost
    inflight: int = 0                                   # units of its calls not yet answered (journal only)


def export_batch(batch: Batch, spent_units: int | None = None, journal: bool = False) -> dict:
    """The batch as exported; ``spent_units`` overrides what it shows as spent (an export holds no running build)."""
    exported = {"batch_id": batch.batch_id, "user_id": batch.user_id, "budget_units": batch.budget_units,
                "domains": list(batch.domains), "builds": list(batch.builds),
                "spent_units": batch.spent_units if spent_units is None else spent_units}
    if journal:
        exported["inflight"] = batch.inflight
    return exported


def parse_batch(raw: dict) -> Batch:
    """A batch from its exported form; ValueError, KeyError or TypeError when it is not one."""
    batch = Batch(raw["batch_id"], raw["user_id"], raw["budget_units"], list(raw["domains"]),
                  list(raw["builds"]), raw["spent_units"], raw.get("inflight", 0))
    ints = (batch.budget_units, batch.spent_units, batch.inflight)
    if not isinstance(batch.batch_id, str) or not isinstance(batch.user_id, str) \
            or any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in ints) \
            or not all(isinstance(d, str) and is_valid_domain(d) for d in batch.domains + batch.builds) \
            or not set(batch.builds) <= set(batch.domains):
        raise ValueError("bad batch")
    return batch
