"""Page versions: what one ready build gathered from one URL, and what held on a given date.

A version holds from its ``true_from``. A later version of the same URL replaces every earlier
version whose ``true_from`` is on or after its own, and ends the latest earlier version it does
not replace on its own ``true_from``. A version without a ``true_from`` holds from no date, and
replaces every earlier version of its URL.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timezone

from .clock import try_parse_timestamp
from .selection import Candidate
from .support import SLOTS

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class PageVersion:
    """One URL as one build gathered it: its ``true_from`` and the candidates its text supports, by slot."""
    url: str
    true_from: str | None
    candidates: tuple[tuple[str, Candidate], ...]


def valid_date(text: object) -> bool:
    """Whether ``text`` is a real calendar date written ``YYYY-MM-DD``."""
    if not isinstance(text, str) or not _DATE.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def page_true_from(header: dict[str, str], published_at: str | None) -> str | None:
    """The page's ``Effective`` date, else the UTC date of its publication time, else None."""
    effective = header.get("Effective", "").strip()
    if valid_date(effective):
        return effective
    return published_date(published_at)


def published_date(published_at: str | None) -> str | None:
    moment = try_parse_timestamp(published_at)
    return moment.astimezone(timezone.utc).date().isoformat() if moment is not None else None


def holding(builds: Iterable[list[PageVersion]], true_at: str) -> dict[str, list[Candidate]]:
    """The candidates, by slot, of every version that holds on ``true_at``; ``builds`` are in build order."""
    chains: dict[str, list[PageVersion]] = {}
    for pages in builds:
        for version in pages:
            chain = chains.setdefault(version.url, [])
            if version.true_from is None:
                chain.clear()
            else:
                while chain and chain[-1].true_from is not None and chain[-1].true_from >= version.true_from:
                    chain.pop()
            chain.append(version)
    found: dict[str, list[Candidate]] = {slot: [] for slot in SLOTS}
    for chain in chains.values():
        for index, version in enumerate(chain):
            ends = chain[index + 1].true_from if index + 1 < len(chain) else None
            if version.true_from is not None and version.true_from <= true_at and (ends is None or true_at < ends):
                for slot, candidate in version.candidates:
                    found[slot].append(candidate)
    return found
