"""A dossier's exported form: stage-3 state, and the upgrade of stage-1 and stage-2 exports.

A stage-3 export keeps every build with the pages it gathered, so ``?as_of=`` and ``/values``
answer after an import as they did before. A stage-1 or stage-2 export keeps only the last
build's fields; that counts as one build that completed ``ready`` at ``researched_at``.
"""
from __future__ import annotations

import copy

from .clock import parse_timestamp, try_parse_timestamp
from .domains import is_valid_domain
from .dossier import BuildRecord, Dossier, iso
from .selection import KINDS, Candidate, candidate_of
from .support import ALL_FIELDS, FIELDS, SLOTS, supported_value
from .versions import PageVersion, published_date, valid_date

HEADCOUNT_VALUES = ("1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10000", "10001+")
ENTRY_TYPES = ("initial", "change", "correction")


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------- export

def export_dossier(dossier: Dossier) -> dict:
    """The dossier as it was before any running build."""
    building = dossier.build is not None
    return {
        "dossier_id": dossier.dossier_id,
        "domain": dossier.domain,
        "state": dossier.outcome,
        "researched_at": iso(dossier.researched_at),
        "spent_units": dossier.spent_before_build if building else dossier.spent_units,
        "fields": copy.deepcopy(dossier.fields),
        "builds": [{
            "time": record.time.isoformat(), "outcome": record.outcome, "spent": record.spent,
            "pages": [{"url": page.url, "true_from": page.true_from,
                       "candidates": [{"slot": slot, "value": c.value, "excerpt": c.excerpt, "provider": c.provider,
                                       "kind": c.kind, "published_at": c.published_at}
                                      for slot, c in page.candidates]} for page in record.pages],
            "fields": copy.deepcopy(record.fields),
        } for record in dossier.builds],
        "history": copy.deepcopy(dossier.history),
    }


# ---------------------------------------------------------------------- stage-3 import

def parse_dossier(raw: dict) -> Dossier:
    """A dossier from a stage-3 export; ValueError, KeyError or TypeError when it is not one."""
    dossier = _parse_identity(raw)
    dossier.outcome = _outcome(raw["state"])
    if not is_int(raw["spent_units"]) or raw["spent_units"] < 0:
        raise ValueError("bad spent_units")
    dossier.spent_units = raw["spent_units"]
    if not isinstance(raw["builds"], list):
        raise ValueError("builds must be a list")
    dossier.builds = [_parse_build(b) for b in raw["builds"]]
    ready = [b for b in dossier.builds if b.outcome == "ready"]
    if ready:
        dossier.fields = copy.deepcopy(ready[-1].fields)
        dossier.researched_at = ready[-1].time
    history = raw["history"]
    if not isinstance(history, dict) or set(history) != set(ALL_FIELDS):
        raise ValueError("history must hold the seven fields")
    dossier.history = {name: [_parse_entry(e) for e in history[name]] for name in ALL_FIELDS}
    dossier.index_first_seen()
    return dossier


def _parse_identity(raw: dict) -> Dossier:
    if not isinstance(raw["dossier_id"], str) or not isinstance(raw["domain"], str) \
            or not is_valid_domain(raw["domain"]):
        raise ValueError("bad dossier")
    return Dossier(raw["dossier_id"], raw["domain"])


def _outcome(state) -> str:
    if state not in ("ready", "failed"):
        raise ValueError("bad dossier state")
    return state


def _parse_build(raw: dict) -> BuildRecord:
    if raw["outcome"] not in ("ready", "failed") or not is_int(raw["spent"]) or raw["spent"] < 0:
        raise ValueError("bad build")
    record = BuildRecord(parse_timestamp(raw["time"]), raw["outcome"], raw["spent"])
    if record.outcome == "ready":
        record.pages = [_parse_page(p) for p in raw["pages"]]
        record.fields = _parse_snapshot(raw["fields"])
    return record


def _parse_page(raw: dict) -> PageVersion:
    true_from = raw["true_from"]
    if not isinstance(raw["url"], str) or (true_from is not None and not valid_date(true_from)):
        raise ValueError("bad page")
    found = []
    for entry in raw["candidates"]:
        if entry["slot"] not in SLOTS:
            raise ValueError("bad candidate slot")
        found.append((entry["slot"], check_candidate(entry["slot"], Candidate(
            entry["value"], raw["url"], entry["excerpt"], entry["provider"], entry["kind"], entry["published_at"],
            true_from=true_from))))
    return PageVersion(raw["url"], true_from, tuple(found))


def _parse_snapshot(raw: dict) -> dict[str, dict]:
    if not isinstance(raw, dict) or set(raw) != set(ALL_FIELDS):
        raise ValueError("fields must be the seven dossier fields")
    for entry in raw.values():
        if entry["status"] not in ("known", "contested", "unknown") or not isinstance(entry["candidates"], list) \
                or not isinstance(entry["citations"], list):
            raise ValueError("bad field")
    return copy.deepcopy(raw)


def _parse_entry(raw: dict) -> dict:
    if raw["type"] not in ENTRY_TYPES or not isinstance(raw["citations"], list):
        raise ValueError("bad history entry")
    parse_timestamp(raw["learned_at"])
    if raw["true_from"] is not None and not valid_date(raw["true_from"]):
        raise ValueError("bad history entry")
    return copy.deepcopy({k: raw[k] for k in ("type", "value", "true_from", "learned_at", "citations")})


def parse_feed_entry(raw: dict) -> dict:
    entry = {k: raw[k] for k in ("seq", "domain", "field", "type", "from", "to", "true_from", "learned_at")}
    if not is_int(entry["seq"]) or entry["seq"] < 1 or entry["field"] not in ALL_FIELDS \
            or entry["type"] not in ("change", "correction") or not isinstance(entry["domain"], str):
        raise ValueError("bad feed entry")
    parse_timestamp(entry["learned_at"])
    return copy.deepcopy(entry)


# ---------------------------------------------------------------------- stage-1 and stage-2 import

def upgrade_dossier(raw: dict) -> Dossier:
    """A dossier from a stage-1 or stage-2 export: one ready build at ``researched_at``."""
    dossier = _parse_identity(raw)
    outcome = _outcome(raw["state"])
    if not is_int(raw["spent_units"]) or raw["spent_units"] < 0:
        raise ValueError("bad spent_units")
    researched = parse_timestamp(raw["researched_at"]) if raw["researched_at"] is not None else None
    found = _upgrade_candidates(raw["fields"], researched, raw["domain"])
    if researched is None:
        if any(found.values()):
            raise ValueError("a dossier never researched has no candidates")
        dossier.spent_units = raw["spent_units"]
    else:
        dossier.complete_build(researched, raw["spent_units"], _pages_of(found))
        dossier.spent_units = raw["spent_units"]
    dossier.outcome = outcome
    return dossier


def _pages_of(found: dict[str, list[Candidate]]) -> list[PageVersion]:
    """One page version per URL; its ``true_from`` follows from the publication time the export records."""
    by_url: dict[str, list[tuple[str, Candidate]]] = {}
    for slot in SLOTS:
        for candidate in found.get(slot, []):
            by_url.setdefault(candidate.url, []).append((slot, candidate))
    pages = []
    for url, items in by_url.items():
        true_from = next((d for d in (published_date(c.published_at) for _, c in items) if d is not None), None)
        pages.append(PageVersion(url, true_from, tuple((slot, _with_true_from(c, true_from)) for slot, c in items)))
    return pages


def _with_true_from(candidate: Candidate, true_from: str | None) -> Candidate:
    return Candidate(candidate.value, candidate.url, candidate.excerpt, candidate.provider, candidate.kind,
                     candidate.published_at, candidate.retrieved_at, true_from, candidate.learned_at)


def _upgrade_candidates(raw: dict, researched_at, domain: str) -> dict[str, list[Candidate]]:
    if set(raw) != set(FIELDS):
        raise ValueError("fields must be the six dossier fields")
    for entry in raw.values():
        if entry["status"] not in ("known", "contested", "unknown"):
            raise ValueError("bad field status")
    if all("candidates" in entry for entry in raw.values()):
        found = {name: [_parse_stage_two_candidate(name, c) for c in raw[name]["candidates"]] for name in FIELDS}
        if any((entry["status"] == "unknown") != (not found[name]) for name, entry in raw.items()):
            raise ValueError("field status does not match its evidence")
        return found
    return _stage_one_candidates(raw, researched_at, domain)


def _stage_one_candidates(raw: dict, researched_at, domain: str) -> dict[str, list[Candidate]]:
    """Candidates of a stage-1 export, which keeps only each field's value and its citations.

    The export holds no served page text, so the text of a citation's page is known only as far
    as its excerpt: that is a candidate for the field it cites and for every other field the
    excerpt supports. They have no kind or publication time.
    """
    found: dict[str, list[Candidate]] = {name: [] for name in FIELDS}
    seen: set[tuple[str, str, object]] = set()

    def add(name: str, value: object, citation: dict) -> None:
        candidate = check_candidate(name, Candidate(value, citation["url"], citation["excerpt"],
                                                    citation["provider"], None, None))
        if (name, candidate.url, candidate.value) not in seen:
            seen.add((name, candidate.url, candidate.value))
            found[name].append(candidate)

    cited = []
    for name in FIELDS:
        entry = raw[name]
        if (entry["status"] == "known") != (entry["value"] is not None and bool(entry["citations"])) \
                or (entry["status"] == "unknown" and entry["citations"]):
            raise ValueError("field status does not match its evidence")
        for citation in entry["citations"]:
            add(name, entry["value"], citation)
            cited.append(citation)
    for citation in cited:
        for name in FIELDS:
            value = supported_value(name, citation["excerpt"], domain)
            if value is not None:
                add(name, value, citation)
    return found


def _parse_stage_two_candidate(name: str, entry: dict) -> Candidate:
    candidate = check_candidate(name, candidate_of(entry))
    if try_parse_timestamp(candidate.retrieved_at) is None and candidate.retrieved_at is not None:
        raise ValueError("bad candidate timestamp")
    return candidate


def check_candidate(name: str, candidate: Candidate) -> Candidate:
    """``candidate`` when it is well formed for field or title ``name``."""
    _check_value(name, candidate.value)
    if not all(isinstance(v, str) for v in (candidate.url, candidate.excerpt, candidate.provider)):
        raise ValueError("bad candidate")
    if candidate.kind is not None and candidate.kind not in KINDS:
        raise ValueError("bad candidate kind")
    if candidate.published_at is not None and try_parse_timestamp(candidate.published_at) is None:
        raise ValueError("bad candidate timestamp")
    return candidate


def _check_value(name: str, value) -> None:
    if name in ("founded_year", "funding_total"):
        ok = is_int(value)
    elif name == "headcount_range":
        ok = value in HEADCOUNT_VALUES
    else:
        ok = isinstance(value, str)
    if not ok:
        raise ValueError(f"bad value for {name}")
