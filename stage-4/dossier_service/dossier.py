"""One dossier: its builds, the selected value of every field, the history of those values and the changes.

A completed build turns the candidates it gathered into the dossier's eight fields. Every field
whose selected value differs from the one before gets a history entry, and a change or correction
also a feed entry (``Dossier.complete_build`` returns those for the store to number).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from datetime import datetime

from .corroboration import corroborated_since
from .selection import (Candidate, executives_of, field_of, investors_of, latest_true_from, rank, same_value,
                        select_by_title, unknown_view)
from .support import ALL_FIELDS, EXEC_TITLES, EXECUTIVES, FIELDS, INVESTORS, SLOTS
from .versions import PageVersion, holding


def unknown_fields() -> dict[str, dict]:
    return {name: unknown_view() for name in ALL_FIELDS}


def iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


@dataclass
class BuildRecord:
    """A finished build: when it was requested, how it ended, what it spent and, if ready, what it gathered."""
    time: datetime
    outcome: str                                # "ready" or "failed"
    spent: int
    pages: list[PageVersion] = field(default_factory=list)
    fields: dict[str, dict] | None = None       # the eight fields as the build left them (ready builds)


@dataclass
class Build:
    """One running build of one dossier; ``batch_id`` names the batch whose budget it shares, if any."""
    epoch: int
    time: datetime
    batch_id: str | None = None


@dataclass
class Dossier:
    dossier_id: str
    domain: str
    builds: list[BuildRecord] = field(default_factory=list)
    history: dict[str, list[dict]] = field(default_factory=lambda: {name: [] for name in ALL_FIELDS})
    fields: dict[str, dict] = field(default_factory=unknown_fields)
    researched_at: datetime | None = None
    spent_units: int = 0
    outcome: str = "failed"          # outcome of the latest finished build
    build: Build | None = None
    spent_before_build: int = 0
    inflight: int = 0                # units of the running build's provider calls not yet answered
    interrupted: dict | None = None  # a build a restart found running: its time, batch and what it had spent
    _first_seen: dict[tuple, str] = field(default_factory=dict)

    @property
    def state(self) -> str:
        return "building" if self.build is not None else self.outcome

    # ------------------------------------------------------------------ completing builds

    def complete_build(self, time: datetime, spent: int, pages: list[PageVersion]) -> list[dict]:
        """Record a build that completed ``ready``; the feed entries (without ``seq``) it adds."""
        moment = time.isoformat()
        by_slot: dict[str, list[Candidate]] = {slot: [] for slot in SLOTS}
        first_seen = dict(self._first_seen)
        for page in pages:
            for slot, candidate in page.candidates:
                learned = first_seen.setdefault(_identity(slot, candidate), moment)
                by_slot[slot].append(replace(candidate, retrieved_at=moment, learned_at=learned))
        first = not self.has_ready_build()
        fields: dict[str, dict] = {}
        entries: dict[str, str] = {}
        ready = [(record.time.isoformat(), record.fields) for record in self.builds if record.outcome == "ready"]
        for name in ALL_FIELDS:
            new = _field_view(name, by_slot)
            if first:
                kind = "initial" if new["value"] is not None else None
            else:
                kind = entry_type(name, self.fields[name], new)
            if kind is not None:
                entries[name] = kind
            if new["value"] is not None:      # an unknown field has no learned_at, whatever its history says
                new["learned_at"] = moment if kind is not None else self.fields[name]["learned_at"]
            new["corroborated_since"] = corroborated_since(name, [(t, f[name]) for t, f in ready] + [(moment, new)])
            fields[name] = new
        feed = []
        for name, kind in entries.items():
            new = fields[name]
            self.history[name].append({"type": kind, "value": new["value"], "true_from": new["true_from"],
                                       "learned_at": moment, "citations": copy.deepcopy(new["citations"])})
            if kind != "initial":
                feed.append({"field": name, "type": kind, "from": self.fields[name]["value"], "to": new["value"],
                             "true_from": new["true_from"], "learned_at": moment})
        self._first_seen = first_seen
        self.builds.append(BuildRecord(time, "ready", spent, pages, fields))
        self.fields = copy.deepcopy(fields)
        self.researched_at = time
        self.outcome = "ready"
        return feed

    def refresh_corroboration(self) -> None:
        """Derive every ready build's ``origins`` and ``corroborated_since`` again from the builds' candidates.

        Used for state imported from an export that predates them or records them unchecked.
        """
        ready = [record for record in self.builds if record.outcome == "ready"]
        for index, record in enumerate(ready):
            for name in ALL_FIELDS:
                view = record.fields[name]
                members = _member_candidates(name, view)
                view.update(origin_keys_of(members))
                view["corroborated_since"] = corroborated_since(
                    name, [(r.time.isoformat(), r.fields[name]) for r in ready[:index + 1]])
        if ready:
            self.fields = copy.deepcopy(ready[-1].fields)

    def complete_failed_build(self, time: datetime, spent: int) -> None:
        self.builds.append(BuildRecord(time, "failed", spent))
        self.outcome = "failed"

    def has_ready_build(self) -> bool:
        return any(b.outcome == "ready" for b in self.builds)

    def index_first_seen(self) -> None:
        """Rebuild which build first gathered each candidate, from the builds in order."""
        self._first_seen = {}
        for record in self.builds:
            if record.outcome == "ready":
                for page in record.pages:
                    for slot, candidate in page.candidates:
                        self._first_seen.setdefault(_identity(slot, candidate), record.time.isoformat())

    # ------------------------------------------------------------------ reading the past

    def snapshot_at(self, as_of: datetime) -> tuple[BuildRecord, int] | None:
        """The latest ready build at or before ``as_of`` (the last of equal times) and the spending to then."""
        done = [b for b in self.builds if b.time <= as_of]
        ready = [b for b in done if b.outcome == "ready"]
        if not ready:
            return None
        return max(enumerate(ready), key=lambda pair: (pair[1].time, pair[0]))[1], sum(b.spent for b in done)

    def values_at(self, true_at: str, as_of: datetime) -> dict[str, dict] | None:
        """For each field the value the evidence known at ``as_of`` says held on ``true_at``."""
        ready = [b for b in self.builds if b.outcome == "ready" and b.time <= as_of]
        if not ready:
            return None
        found = holding([b.pages for b in ready], true_at)
        values = {}
        for name in FIELDS:
            ranked = rank(found[name])
            values[name] = _value_view(ranked[0], ranked) if ranked else _no_value()
        chosen = select_by_title(found)
        if chosen:
            selected = [pick for _, pick, _ in chosen]
            citations = [{"url": c.url, "excerpt": c.excerpt, "provider": c.provider}
                         for _, pick, ranked in chosen for c in ranked if same_value(c.value, pick.value)]
            values[EXECUTIVES] = {"value": [{"title": t, "name": p.value.strip()} for t, p, _ in chosen],
                                  "true_from": latest_true_from(selected), "citations": citations}
        else:
            values[EXECUTIVES] = _no_value()
        investors = investors_of(found[INVESTORS])
        values[INVESTORS] = {key: investors[key] for key in ("value", "true_from", "citations")}
        return values


def _field_view(name: str, by_slot: dict[str, list[Candidate]]) -> dict:
    if name == EXECUTIVES:
        return executives_of(by_slot)
    if name == INVESTORS:
        return investors_of(by_slot[INVESTORS])
    return field_of(by_slot[name])


def _member_candidates(name: str, view: dict) -> list[list[dict]]:
    """The candidates (as views) of each member of a field's value."""
    value = view["value"]
    if value is None:
        return []
    candidates = view["candidates"]
    if name == EXECUTIVES:
        return [[c for c in candidates if c["title"] == m["title"] and c["value"].strip() == m["name"]] for m in value]
    if name == INVESTORS:
        return [[c for c in candidates if c["value"] == member] for member in value]
    return [[c for c in candidates if same_value(c["value"], value)]]


def origin_keys_of(members: list[list[dict]]) -> dict:
    """``origins`` and ``corroborated`` from candidates as the API shows them."""
    return {"origins": sorted({c["origin"] for member in members for c in member}),
            "corroborated": bool(members) and all(len({c["origin"] for c in member}) >= 2 for member in members)}


def _identity(slot: str, candidate: Candidate) -> tuple:
    return slot, type(candidate.value).__name__, candidate.value, candidate.url, candidate.provider


def _no_value() -> dict:
    return {"value": None, "true_from": None, "citations": []}


def _value_view(selected: Candidate, ranked: list[Candidate]) -> dict:
    return {"value": selected.value.strip() if isinstance(selected.value, str) else selected.value,
            "true_from": selected.true_from,
            "citations": [{"url": c.url, "excerpt": c.excerpt, "provider": c.provider}
                          for c in ranked if same_value(c.value, selected.value)]}


# ---------------------------------------------------------------------- what counts as a change

def entry_type(name: str, earlier: dict, new: dict) -> str | None:
    """``change`` or ``correction`` when ``new`` differs from ``earlier`` for field ``name``, else None."""
    if name == EXECUTIVES:
        return _executives_entry_type(earlier, new)
    if name == INVESTORS:
        return _investors_entry_type(earlier, new)
    if same_value(earlier["value"], new["value"]):
        return None
    both_present = earlier["value"] is not None and new["value"] is not None
    return "correction" if both_present and _is_correction(earlier["true_from"], new["true_from"]) else "change"


def _is_correction(earlier_from: str | None, new_from: str | None) -> bool:
    """Whether a new value dated ``new_from`` corrects one dated ``earlier_from``: it holds no later."""
    return earlier_from is not None and new_from is not None and new_from <= earlier_from


def _members(value: dict) -> dict[str, tuple[str, str | None]]:
    """title -> (name, true_from of the selected candidate of that title)."""
    out = {}
    for candidate in value["candidates"]:
        if candidate["selected"]:
            out[candidate["title"]] = (candidate["value"], candidate["true_from"])
    return out


def _executives_entry_type(earlier: dict, new: dict) -> str | None:
    before, after = _members(earlier), _members(new)
    differing = [t for t in EXEC_TITLES if before.get(t, (None, None))[0] != after.get(t, (None, None))[0]]
    if not differing:
        return None
    corrections = all(t in before and t in after and _is_correction(before[t][1], after[t][1]) for t in differing)
    return "correction" if corrections else "change"


def _investors_entry_type(earlier: dict, new: dict) -> str | None:
    """A name that left is never a correction; a name that arrived is one when it holds no later than the earlier value."""
    before, after = set(earlier["value"] or []), set(new["value"] or [])
    if before == after:
        return None
    if before - after or earlier["true_from"] is None:
        return "change"
    arrived = {name: None for name in after - before}
    for candidate in new["candidates"]:
        if candidate["selected"] and candidate["value"] in arrived and candidate["true_from"] is not None:
            known = arrived[candidate["value"]]
            arrived[candidate["value"]] = candidate["true_from"] if known is None else min(known, candidate["true_from"])
    return "correction" if all(_is_correction(earlier["true_from"], found) for found in arrived.values()) else "change"
