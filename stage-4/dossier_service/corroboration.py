"""``corroborated_since``: when a field's selected value first stood on two independent origins.

The standing origins of a selected value are those of every candidate with that value that any
ready build has gathered since the value became the selected value, whether or not a later build
gathered it again. For ``executives`` and ``investors`` the same holds member by member, counted
from the build after which the member last became one; the field is corroborated since the build
after which every member is.

A field is read here from the views its builds left (``value``, ``candidates``, ``origin``), so the
answer follows from the builds alone and can be recomputed after an import.
"""
from __future__ import annotations

from .selection import same_value
from .support import EXECUTIVES, INVESTORS

ORIGINS_NEEDED = 2

Series = list[tuple[str, dict]]       # (time of the build, the field as the build left it), ready builds in order


def _members(name: str, view: dict) -> list[tuple]:
    """The members of a field's value, as comparable keys."""
    value = view["value"]
    if value is None:
        return []
    if name == EXECUTIVES:
        return [(member["title"], member["name"]) for member in value]
    if name == INVESTORS:
        return [(member,) for member in value]
    return [(type(value).__name__, value.strip() if isinstance(value, str) else value)]


def _origins(name: str, view: dict, member: tuple) -> set[str]:
    """The origins of the candidates of ``member`` in ``view``."""
    found = set()
    for candidate in view["candidates"]:
        if name == EXECUTIVES:
            same = (candidate["title"], candidate["value"].strip()) == member
        elif name == INVESTORS:
            same = candidate["value"] == member[0]
        else:
            same = same_value(candidate["value"], view["value"])
        if same and candidate.get("origin") is not None:
            found.add(candidate["origin"])
    return found


def corroborated_since(name: str, series: Series) -> str | None:
    """The time of the earliest build after which every member of the last view has had two standing origins."""
    last = len(series) - 1
    members = _members(name, series[last][1])
    if not members:
        return None
    since = 0
    for member in members:
        start = last
        while start > 0 and member in _members(name, series[start - 1][1]):
            start -= 1
        standing: set[str] = set()
        for index in range(start, last + 1):
            standing |= _origins(name, series[index][1], member)
            if len(standing) >= ORIGINS_NEEDED:
                since = max(since, index)
                break
        else:
            return None
    return series[since][0]
