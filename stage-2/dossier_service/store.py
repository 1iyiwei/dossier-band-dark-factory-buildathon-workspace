"""All service state behind one lock: users, tokens, dossiers, builds, idempotency, export/import.

Every request takes the lock briefly; builds do their provider calls outside it and only
touch state through ``_add_spent`` and ``_finish_build``, which ignore a build whose state
was replaced (reset or import) or superseded.
"""
from __future__ import annotations

import copy
import logging
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from .builder import BuildResult
from .clock import Clock, parse_timestamp, try_parse_timestamp
from .domains import is_valid_domain
from .errors import ApiError, malformed, validation_failed
from .passwords import hash_password, verify_password
from .selection import KINDS, Candidate, candidate_of, field_of
from .support import FIELDS

log = logging.getLogger("dossier.store")

BuildFn = Callable[[str, Callable[[int], None], Callable[[], bool]], BuildResult]

HEADCOUNT_VALUES = ("1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10000", "10001+")
UNKNOWN_FIELD = {"value": None, "status": "unknown", "citations": [], "candidates": []}
EXPORT_TRACK = "dossier"
EXPORT_VERSION = 1


def unknown_fields() -> dict[str, dict]:
    return {name: copy.deepcopy(UNKNOWN_FIELD) for name in FIELDS}


@dataclass
class Build:
    """One running build of one dossier."""
    epoch: int
    time: datetime


@dataclass
class Dossier:
    dossier_id: str
    domain: str
    fields: dict[str, dict] = field(default_factory=unknown_fields)
    researched_at: datetime | None = None
    spent_units: int = 0
    outcome: str = "failed"          # outcome of the latest finished build
    build: Build | None = None
    spent_before_build: int = 0

    @property
    def state(self) -> str:
        return "building" if self.build is not None else self.outcome


@dataclass
class IdempotencyRecord:
    fingerprint: str
    status: int
    body: dict


class Store:
    def __init__(self, build_fn: BuildFn) -> None:
        self._build_fn = build_fn
        self._lock = threading.RLock()
        self.clock = Clock()
        self._epoch = 0
        self._users: dict[str, dict] = {}
        self._emails: dict[str, str] = {}
        self._tokens: dict[str, str] = {}
        self._dossiers: dict[str, Dossier] = {}
        self._idempotency: dict[tuple[str, str, str, str], IdempotencyRecord] = {}
        self._dossier_counter = 0

    # ------------------------------------------------------------------ reset

    def reset(self, fixture: dict) -> None:
        now, users = _parse_fixture(fixture)
        hashed = [{**user, "password_hash": hash_password(user["password"])} for user in users]
        for user in hashed:
            del user["password"]
        with self._lock:
            self._replace_state(
                users={u["id"]: u for u in hashed}, tokens={}, dossiers={}, idempotency={}, counter=0)
            self.clock.reset(now)

    def _replace_state(self, users, tokens, dossiers, idempotency, counter) -> None:
        self._epoch += 1
        self._users = users
        self._emails = {u["email"].lower(): u["id"] for u in users.values()}
        self._tokens = tokens
        self._dossiers = dossiers
        self._idempotency = idempotency
        self._dossier_counter = counter

    # ------------------------------------------------------------------ auth

    def signup(self, email: str, password: str, display_name: str) -> dict:
        digest = hash_password(password)
        with self._lock:
            if email.lower() in self._emails:
                raise ApiError(409, "email_taken", "email already registered")
            user_id = self._new_user_id()
            user = {"id": user_id, "email": email, "display_name": display_name, "password_hash": digest}
            self._users[user_id] = user
            self._emails[email.lower()] = user_id
            return self._session(user)

    def login(self, email: str, password: str) -> dict:
        with self._lock:
            user = self._users.get(self._emails.get(email.lower(), ""))
        if user is None or not verify_password(password, user["password_hash"]):
            raise ApiError(401, "unauthenticated", "wrong email or password")
        with self._lock:
            return self._session(user)

    def authenticate(self, token: str | None) -> str:
        with self._lock:
            user_id = self._tokens.get(token or "")
        if user_id is None:
            raise ApiError(401, "unauthenticated", "missing or unknown bearer token")
        return user_id

    def _session(self, user: dict) -> dict:
        token = secrets.token_urlsafe(32)
        self._tokens[token] = user["id"]
        return {"user_id": user["id"], "display_name": user["display_name"], "token": token}

    def _new_user_id(self) -> str:
        while True:
            user_id = "u_" + secrets.token_hex(6)
            if user_id not in self._users:
                return user_id

    # ------------------------------------------------------------------ idempotent writes

    def idempotent(self, user_id: str, method: str, path: str, key: str, fingerprint: str,
                   action: Callable[[], tuple[int, dict]]) -> tuple[int, dict]:
        """Run ``action`` once per (user, method, path, key); replay its response afterwards.

        A 4xx raised by ``action`` claims nothing, so the key stays reusable.
        """
        with self._lock:
            slot = (user_id, method, path, key)
            record = self._idempotency.get(slot)
            if record is not None:
                if record.fingerprint != fingerprint:
                    raise ApiError(409, "idempotency_key_reuse", "idempotency key used with a different body")
                return 200, copy.deepcopy(record.body)
            status, body = action()
            self._idempotency[slot] = IdempotencyRecord(fingerprint, status, copy.deepcopy(body))
            return status, body

    # ------------------------------------------------------------------ dossiers

    def start_dossier(self, domain: str) -> tuple[int, dict]:
        """POST /dossiers: create and build, or report the existing dossier. Call under ``idempotent``."""
        with self._lock:
            dossier = self._dossiers.get(domain)
            if dossier is not None:
                return 200, self._summary(dossier)
            self._dossier_counter += 1
            dossier = Dossier(f"d_{self._dossier_counter}", domain)
            self._dossiers[domain] = dossier
            self._start_build(dossier)
            return 202, self._summary(dossier)

    def refresh_dossier(self, domain: str) -> tuple[int, dict]:
        """POST /dossiers/{domain}/refresh. Call under ``idempotent``."""
        with self._lock:
            dossier = self._dossiers.get(domain)
            if dossier is None:
                raise ApiError(404, "not_found", "no dossier for this domain")
            if dossier.build is None:
                self._start_build(dossier)
            return 202, self._summary(dossier)

    def get_dossier(self, domain: str) -> dict:
        with self._lock:
            dossier = self._dossiers.get(domain)
            if dossier is None:
                raise ApiError(404, "not_found", "no dossier for this domain")
            return {
                **self._summary(dossier),
                "researched_at": _iso(dossier.researched_at),
                "spent_units": dossier.spent_units,
                "fields": copy.deepcopy(dossier.fields),
            }

    def list_dossiers(self, q: str, limit: int, offset: int) -> dict:
        needle = q.lower()
        with self._lock:
            matching = [d for _, d in sorted(self._dossiers.items())
                        if needle in d.domain or needle in (d.fields["legal_name"]["value"] or "").lower()]
            page = matching[offset:offset + limit]
            return {
                "dossiers": [{
                    **self._summary(d),
                    "legal_name": d.fields["legal_name"]["value"],
                    "researched_at": _iso(d.researched_at),
                    "spent_units": d.spent_units,
                } for d in page],
                "has_more": offset + len(page) < len(matching),
            }

    @staticmethod
    def _summary(dossier: Dossier) -> dict:
        return {"dossier_id": dossier.dossier_id, "domain": dossier.domain, "state": dossier.state}

    # ------------------------------------------------------------------ builds

    def _start_build(self, dossier: Dossier) -> None:
        build = Build(self._epoch, self.clock.now())
        dossier.build = build
        dossier.spent_before_build = dossier.spent_units
        threading.Thread(target=self._run_build, args=(dossier, build), daemon=True,
                         name=f"build-{dossier.domain}").start()

    def _current(self, dossier: Dossier, build: Build) -> bool:
        return build.epoch == self._epoch and dossier.build is build

    def _run_build(self, dossier: Dossier, build: Build) -> None:
        result: BuildResult | None = None
        try:
            result = self._build_fn(dossier.domain, lambda units: self._add_spent(dossier, build, units),
                                    lambda: not self._is_current(dossier, build))
        except Exception:   # noqa: BLE001 - a crashed build must still end, as failed
            log.exception("build of %s crashed", dossier.domain)
        with self._lock:
            if not self._current(dossier, build):
                return
            dossier.build = None
            if result is not None and result.succeeded:
                retrieved_at = build.time.isoformat()
                dossier.fields = {name: field_of(result.candidates[name], retrieved_at) for name in FIELDS}
                dossier.researched_at = build.time
                dossier.outcome = "ready"
            else:
                dossier.outcome = "failed"

    def _is_current(self, dossier: Dossier, build: Build) -> bool:
        with self._lock:
            return self._current(dossier, build)

    def _add_spent(self, dossier: Dossier, build: Build, units: int) -> None:
        with self._lock:
            if self._current(dossier, build):
                dossier.spent_units += units

    # ------------------------------------------------------------------ export / import

    def export_state(self) -> dict:
        """A deep, atomic snapshot. A running build is not in it: the dossier is as it was before."""
        with self._lock:
            dossiers = []
            for dossier in sorted(self._dossiers.values(), key=lambda d: d.domain):
                building = dossier.build is not None
                dossiers.append({
                    "dossier_id": dossier.dossier_id,
                    "domain": dossier.domain,
                    "state": dossier.outcome,
                    "fields": copy.deepcopy(dossier.fields),
                    "researched_at": _iso(dossier.researched_at),
                    "spent_units": dossier.spent_before_build if building else dossier.spent_units,
                })
            state = {
                "users": copy.deepcopy(list(self._users.values())),
                "tokens": dict(self._tokens),
                "dossiers": dossiers,
                "idempotency": [{"user_id": u, "method": m, "path": p, "key": k,
                                 "fingerprint": r.fingerprint, "status": r.status,
                                 "body": copy.deepcopy(r.body)}
                                for (u, m, p, k), r in self._idempotency.items()],
                "dossier_counter": self._dossier_counter,
            }
            return {"track": EXPORT_TRACK, "format_version": EXPORT_VERSION, "state": state}

    def import_state(self, document: dict) -> None:
        """Replace every piece of state with an export; invalid input changes nothing."""
        if document.get("track") != EXPORT_TRACK or not _is_int(document.get("format_version")) \
                or document["format_version"] != EXPORT_VERSION:
            raise validation_failed("not a dossier export of format version 1")
        state = document.get("state")
        if not isinstance(state, dict):
            raise validation_failed("state must be an object")
        try:
            users, tokens, dossiers, idempotency, counter = _parse_state(copy.deepcopy(state))
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise validation_failed(f"invalid state: {error}") from None
        with self._lock:
            self._replace_state(users, tokens, dossiers, idempotency, counter)


# ---------------------------------------------------------------------- parsing helpers

def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_fixture(fixture: dict) -> tuple[datetime, list[dict]]:
    if "now" not in fixture:
        raise validation_failed("fixture needs now")
    if not isinstance(fixture["now"], str):
        raise malformed("now must be a string")
    now = parse_timestamp(fixture["now"])
    raw_users = fixture.get("users", [])
    if not isinstance(raw_users, list):
        raise malformed("users must be a list")
    users, ids, emails = [], set(), set()
    for raw in raw_users:
        if not isinstance(raw, dict):
            raise malformed("each user must be an object")
        user = {}
        for name in ("id", "email", "password", "display_name"):
            if name not in raw:
                raise validation_failed(f"user needs {name}")
            value = raw[name]
            if not isinstance(value, str):
                raise malformed(f"user {name} must be a string")
            user[name] = value
        if not user["id"] or user["id"] in ids or user["email"].lower() in emails:
            raise validation_failed("users need distinct ids and emails")
        ids.add(user["id"])
        emails.add(user["email"].lower())
        users.append(user)
    return now, users


def _parse_fields(raw: dict, researched_at: datetime | None) -> dict[str, dict]:
    """The fields of an exported dossier, recomputed from their candidates by the selection rule.

    A field of a stage-1 export has no candidates: its citations, which a provider served and
    which support its value, become its candidates, with no kind or publication time and
    retrieved when the dossier was last researched.
    """
    if set(raw) != set(FIELDS):
        raise ValueError("fields must be the six dossier fields")
    retrieved_at = researched_at.isoformat() if researched_at is not None else None
    out = {}
    for name in FIELDS:
        entry = raw[name]
        value, status = entry["value"], entry["status"]
        if status not in ("known", "contested", "unknown"):
            raise ValueError("bad field status")
        if "candidates" in entry:
            candidates = [_parse_candidate(name, c) for c in entry["candidates"]]
        elif status == "known":
            candidates = [_parse_candidate(name, {**c, "value": value, "kind": None, "published_at": None,
                                                  "retrieved_at": retrieved_at}) for c in entry["citations"]]
        else:
            candidates = []
        if (status == "unknown") != (not candidates):
            raise ValueError("field status does not match its evidence")
        out[name] = field_of(candidates)
    return out


def _parse_candidate(name: str, entry: dict) -> Candidate:
    candidate = candidate_of(entry)
    _check_value(name, candidate.value)
    if not all(isinstance(v, str) for v in (candidate.url, candidate.excerpt, candidate.provider)):
        raise ValueError("bad candidate")
    if candidate.kind is not None and candidate.kind not in KINDS:
        raise ValueError("bad candidate kind")
    for stamp in (candidate.published_at, candidate.retrieved_at):
        if stamp is not None and try_parse_timestamp(stamp) is None:
            raise ValueError("bad candidate timestamp")
    return candidate


def _check_value(name: str, value) -> None:
    if name in ("founded_year", "funding_total"):
        ok = _is_int(value)
    elif name == "headcount_range":
        ok = value in HEADCOUNT_VALUES
    else:
        ok = isinstance(value, str)
    if not ok:
        raise ValueError(f"bad value for {name}")


def _parse_state(state: dict):
    users: dict[str, dict] = {}
    for raw in state["users"]:
        user = {k: raw[k] for k in ("id", "email", "display_name", "password_hash")}
        if not all(isinstance(v, str) for v in user.values()) or user["id"] in users:
            raise ValueError("bad user")
        users[user["id"]] = user
    if len({u["email"].lower() for u in users.values()}) != len(users):
        raise ValueError("duplicate email")
    tokens = state["tokens"]
    if not isinstance(tokens, dict) or any(not isinstance(v, str) or v not in users for v in tokens.values()):
        raise ValueError("bad tokens")
    dossiers: dict[str, Dossier] = {}
    ids = set()
    for raw in state["dossiers"]:
        if raw["state"] not in ("ready", "failed"):
            raise ValueError("bad dossier state")
        if not isinstance(raw["dossier_id"], str) or not isinstance(raw["domain"], str) \
                or not is_valid_domain(raw["domain"]) or not _is_int(raw["spent_units"]) \
                or raw["spent_units"] < 0 or raw["domain"] in dossiers or raw["dossier_id"] in ids:
            raise ValueError("bad dossier")
        ids.add(raw["dossier_id"])
        researched = parse_timestamp(raw["researched_at"]) if raw["researched_at"] is not None else None
        dossiers[raw["domain"]] = Dossier(
            raw["dossier_id"], raw["domain"], _parse_fields(raw["fields"], researched), researched,
            raw["spent_units"], raw["state"])
    idempotency = {}
    for raw in state["idempotency"]:
        slot = tuple(raw[k] for k in ("user_id", "method", "path", "key"))
        if not all(isinstance(v, str) for v in slot) or not isinstance(raw["body"], dict) \
                or not isinstance(raw["fingerprint"], str) or not _is_int(raw["status"]):
            raise ValueError("bad idempotency record")
        idempotency[slot] = IdempotencyRecord(raw["fingerprint"], raw["status"], raw["body"])
    counter = state["dossier_counter"]
    if not _is_int(counter) or counter < 0:
        raise ValueError("bad counter")
    return users, dict(tokens), dossiers, idempotency, counter
