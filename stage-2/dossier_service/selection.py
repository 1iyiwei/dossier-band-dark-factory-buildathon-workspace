"""Candidates and the selection rule: which value each field holds, and why.

A field's candidates are ranked by the fixed rule of the specification; the highest-ranked
one is selected. Nothing else decides a field's value, so the same candidates always give
the same field.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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


def field_of(candidates: list[Candidate], retrieved_at: str | None = None) -> dict:
    """The API shape of one field: its selected value, status, citations and ranked candidates."""
    ranked = rank(candidates)
    if not ranked:
        return {"value": None, "status": "unknown", "citations": [], "candidates": []}
    selected = ranked[0]
    chosen = [c for c in ranked if same_value(c.value, selected.value)]
    return {
        "value": _canonical(selected.value),
        "status": "known" if len(chosen) == len(ranked) else "contested",
        "citations": [{"url": c.url, "excerpt": c.excerpt, "provider": c.provider} for c in chosen],
        "candidates": [{
            "value": _canonical(c.value), "url": c.url, "excerpt": c.excerpt, "provider": c.provider,
            "kind": c.kind, "published_at": c.published_at,
            "retrieved_at": c.retrieved_at if c.retrieved_at is not None else retrieved_at,
            "selected": c is selected,
        } for c in ranked],
    }


def candidate_of(entry: dict) -> Candidate:
    """A candidate from its API (or exported) form."""
    return Candidate(entry["value"], entry["url"], entry["excerpt"], entry["provider"],
                     entry["kind"], entry["published_at"], entry["retrieved_at"])
