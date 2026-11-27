"""Candidates and the selection rule: which value each field holds, and why.

A field's candidates are ranked by the fixed rule of the specification; the highest-ranked
one is selected. Nothing else decides a field's value, so the same candidates always give
the same field.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .support import EXEC_TITLES

from .clock import try_parse_timestamp

KINDS = ("own", "filing", "news", "aggregator")
PROVIDER_ORDER = ("nimble", "tavily", "kernel", "browserbase")
_AUTHORITY = {"own": 0, "filing": 0, "news": 1, "aggregator": 2}
_LOWEST_AUTHORITY = 2          # an imported candidate has no kind and the authority of an aggregator
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECOND = timedelta(microseconds=1)


@dataclass(frozen=True)
class Candidate:
    """One value for one field, supported by one excerpt of one page."""
    value: object
    url: str
    excerpt: str
    provider: str
    kind: str | None
    published_at: str | None
    retrieved_at: str | None = None
    true_from: str | None = None        # YYYY-MM-DD from which the page says the value holds
    learned_at: str | None = None       # the first build that gathered this value from this page and provider


def same_value(a: object, b: object) -> bool:
    return _canonical(a) == _canonical(b) and type(_canonical(a)) is type(_canonical(b))


def _canonical(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _rank_key(candidate: Candidate) -> tuple:
    authority = _AUTHORITY.get(candidate.kind, _LOWEST_AUTHORITY)
    published = try_parse_timestamp(candidate.published_at)
    recency = (1, 0) if published is None else (0, -((published - _EPOCH) // _MICROSECOND))
    provider = PROVIDER_ORDER.index(candidate.provider) if candidate.provider in PROVIDER_ORDER \
        else len(PROVIDER_ORDER)
    value = _canonical(candidate.value)
    value_key = (0, value, "") if isinstance(value, int) else (1, 0, str(value))
    return authority, recency, candidate.url, provider, value_key


def rank(candidates: list[Candidate]) -> list[Candidate]:
    """The candidates, best first: authority, then recency, then URL, provider and value."""
    return sorted(candidates, key=_rank_key)


def _candidate_view(candidate: Candidate, selected: Candidate, title: str | None = None) -> dict:
    view = {"title": title} if title is not None else {}
    return {**view,
            "value": _canonical(candidate.value), "url": candidate.url, "excerpt": candidate.excerpt,
            "provider": candidate.provider, "kind": candidate.kind, "published_at": candidate.published_at,
            "retrieved_at": candidate.retrieved_at, "true_from": candidate.true_from,
            "learned_at": candidate.learned_at, "selected": candidate is selected}


def _citations(candidates: list[Candidate]) -> list[dict]:
    return [{"url": c.url, "excerpt": c.excerpt, "provider": c.provider} for c in candidates]


def field_of(candidates: list[Candidate], learned_at: str | None = None) -> dict:
    """The API shape of one field: its selected value, status, citations and ranked candidates.

    ``learned_at`` is when the service first had the selected value; an unknown field has none.
    """
    ranked = rank(candidates)
    if not ranked:
        return {"value": None, "status": "unknown", "true_from": None, "learned_at": None,
                "citations": [], "candidates": []}
    selected = ranked[0]
    chosen = [c for c in ranked if same_value(c.value, selected.value)]
    return {
        "value": _canonical(selected.value),
        "status": "known" if len(chosen) == len(ranked) else "contested",
        "true_from": selected.true_from,
        "learned_at": learned_at,
        "citations": _citations(chosen),
        "candidates": [_candidate_view(c, selected) for c in ranked],
    }


def select_by_title(by_title: dict[str, list[Candidate]]) -> list[tuple[str, Candidate, list[Candidate]]]:
    """For each executive title that has candidates, in order: the title, its selected candidate and all ranked."""
    out = []
    for title in EXEC_TITLES:
        ranked = rank(by_title.get(title, []))
        if ranked:
            out.append((title, ranked[0], ranked))
    return out


def latest_true_from(members: list[Candidate]) -> str | None:
    """The latest ``true_from`` of the members' candidates; None when there is no member or any has none."""
    if not members or any(m.true_from is None for m in members):
        return None
    return max(m.true_from for m in members)


def executives_of(by_title: dict[str, list[Candidate]], learned_at: str | None = None) -> dict:
    """The ``executives`` field: one member per title that has a selected person."""
    chosen = select_by_title(by_title)
    if not chosen:
        return {"value": None, "status": "unknown", "true_from": None, "learned_at": None,
                "citations": [], "candidates": []}
    citations, candidates = [], []
    contested = False
    for title, selected, ranked in chosen:
        same = [c for c in ranked if same_value(c.value, selected.value)]
        contested = contested or len(same) != len(ranked)
        citations += _citations(same)
        candidates += [_candidate_view(c, selected, title) for c in ranked]
    return {
        "value": [{"title": title, "name": _canonical(selected.value)} for title, selected, _ in chosen],
        "status": "contested" if contested else "known",
        "true_from": latest_true_from([selected for _, selected, _ in chosen]),
        "learned_at": learned_at,
        "citations": citations,
        "candidates": candidates,
    }


def candidate_of(entry: dict) -> Candidate:
    """A candidate from its API (or exported) form."""
    return Candidate(entry["value"], entry["url"], entry["excerpt"], entry["provider"],
                     entry["kind"], entry["published_at"], entry.get("retrieved_at"),
                     entry.get("true_from"), entry.get("learned_at"))
