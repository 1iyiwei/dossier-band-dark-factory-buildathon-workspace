"""All service state behind one lock: users, tokens, dossiers, the change feed, idempotency, export/import.

Every request takes the lock briefly; builds do their provider calls outside it and only
touch state through their ledger (``_reserve``, ``_settle``) and ``_run_build``, which ignore a build whose state
was replaced (reset or import) or superseded. Every change is written to the journal
(``persistence.py``) before the lock is released, so no request is answered with state a
restart would lose.
"""
from __future__ import annotations

import copy
import logging
import secrets
import threading
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from .batches import Batch, export_batch, parse_batch
from .builder import BuildResult
from .clock import Clock, parse_timestamp
from .codec import export_dossier, is_int, parse_dossier, parse_feed_entry, upgrade_dossier
from .config import BUILD_BUDGET_UNITS
from .dossier import Build, Dossier, iso
from .errors import ApiError, malformed, validation_failed
from .ledger import BudgetExhausted, Ledger
from .passwords import hash_password, verify_password
from .persistence import COMPACT_BYTES, Journal
from .support import ALL_FIELDS

log = logging.getLogger("dossier.store")

BuildFn = Callable[[str, Ledger, Callable[[], bool]], BuildResult]

EXPORT_TRACK = "dossier"
EXPORT_VERSION = 1


@dataclass
class IdempotencyRecord:
    fingerprint: str
    status: int
    body: dict


class _BuildFailed(Exception):
    """The build gathered nothing: no provider call was answered."""


@dataclass
class State:
    """Everything the service remembers, apart from its clock and its running builds."""
    users: dict[str, dict] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)
    dossiers: dict[str, Dossier] = field(default_factory=dict)
    idempotency: dict[tuple[str, str, str, str], IdempotencyRecord] = field(default_factory=dict)
    counter: int = 0
    feed: list[dict] = field(default_factory=list)
    next_seq: int = 1
    batches: dict[str, Batch] = field(default_factory=dict)
    batch_counter: int = 0


class Store:
    def __init__(self, build_fn: BuildFn, journal: Journal | None = None) -> None:
        self._build_fn = build_fn
        self._lock = threading.RLock()
        self.clock = Clock()
        self._epoch = 0
        self._journal = journal
        self._pending: dict[tuple[str, object], None] = {}     # records changed since the last write
        self._full = True                                       # the next write is a whole snapshot
        self._feed_written = 0
        self._adopt(State())
        if journal is not None:
            self._restore()

    def _adopt(self, state: State) -> None:
        self._epoch += 1
        self._users = state.users
        self._emails = {u["email"].lower(): u["id"] for u in state.users.values()}
        self._tokens = state.tokens
        self._dossiers = state.dossiers
        self._idempotency = state.idempotency
        self._dossier_counter = state.counter
        self._feed = state.feed
        self._next_seq = state.next_seq
        self._batches = state.batches
        self._batch_counter = state.batch_counter

    # ------------------------------------------------------------------ durability

    def _restore(self) -> None:
        """Load what the journal holds; a journal that cannot be read starts the service empty."""
        snapshot, batches = self._journal.load()
        clock = None
        if snapshot is not None:
            try:
                state = _parse_state(copy.deepcopy(snapshot["export"]["state"]))
                clock = snapshot["clock"]
                for batch in batches:
                    for kind, payload in batch:
                        clock = _apply_record(state, kind, payload, clock)
                self._adopt(state)
                self._recover_interrupted()
                self.clock.restore(parse_timestamp(clock) if clock is not None else None)
            except (KeyError, TypeError, ValueError, AttributeError, ApiError):
                log.exception("the journal is not readable; starting empty")
                self._adopt(State())
        with self._lock:
            self._persist()

    def _recover_interrupted(self) -> None:
        """A build the stop found running is over: it ends ``failed``, leaving the fields as they were.

        Every unit it had spent, or had in flight (a call the provider may have billed), stays counted,
        for its dossier and for its batch.
        """
        for dossier in self._dossiers.values():
            if dossier.interrupted is not None:
                units = dossier.interrupted["spent"] + dossier.interrupted["inflight"]
                dossier.spent_units += units
                dossier.complete_failed_build(parse_timestamp(dossier.interrupted["time"]), units)
                dossier.interrupted = None
        for batch in self._batches.values():
            batch.spent_units += batch.inflight
            batch.inflight = 0

    def _mark(self, kind: str, key: object) -> None:
        self._pending[(kind, key)] = None

    def _persist(self, sync: bool = True) -> None:
        """Write the changes since the last write to disk. Call with the lock held, before answering."""
        if self._journal is None:
            return
        try:
            if self._full or self._journal.size > COMPACT_BYTES:
                self._journal.rewrite(self._snapshot())
                self._full = False
            else:
                self._journal.append(self._records(), sync)
            self._pending.clear()
            self._feed_written = len(self._feed)
        except Exception:   # noqa: BLE001 - the request still stands; the next write is a whole snapshot
            log.exception("could not write the journal")
            self._full = True

    def _snapshot(self) -> dict:
        return {"export": self.export_state(journal=True), "clock": iso(self.clock.fixed())}

    def _records(self) -> list:
        records: list = []
        for kind, key in self._pending:
            if kind == "user":
                records.append(["user", copy.deepcopy(self._users[key])])
            elif kind == "token":
                records.append(["token", [key, self._tokens[key]]])
            elif kind == "dossier":
                records.append(["dossier", export_dossier(self._dossiers[key], running=True)])
            elif kind == "batch":
                records.append(["batch", export_batch(self._batches[key], journal=True)])
            elif kind == "progress":
                dossier = self._dossiers[key]
                batch = self._batches.get(dossier.build.batch_id) if dossier.build is not None else None
                records.append(["progress", {
                    "domain": key, "spent": dossier.spent_units - dossier.spent_before_build,
                    "inflight": dossier.inflight, "batch": None if batch is None else batch.batch_id,
                    "batch_spent": 0 if batch is None else batch.spent_units,
                    "batch_inflight": 0 if batch is None else batch.inflight}])
            elif kind == "idempotency":
                records.append(["idempotency", _idempotency_entry(key, self._idempotency[key])])
        if len(self._feed) > self._feed_written:
            records.append(["feed", copy.deepcopy(self._feed[self._feed_written:])])
        records.append(["meta", {"dossier_counter": self._dossier_counter, "next_seq": self._next_seq,
                                 "batch_counter": self._batch_counter, "clock": iso(self.clock.fixed())}])
        return records

    # ------------------------------------------------------------------ reset and clock

    def reset(self, fixture: dict) -> None:
        now, users = _parse_fixture(fixture)
        hashed = [{**user, "password_hash": hash_password(user["password"])} for user in users]
        for user in hashed:
            del user["password"]
        with self._lock:
            self._adopt(State(users={u["id"]: u for u in hashed}))
            self.clock.reset(now)
            self._full = True
            self._persist()

    def advance_clock(self, now: datetime) -> None:
        with self._lock:
            self.clock.advance_to(now)
            self._persist()

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
            self._mark("user", user_id)
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
        self._mark("token", token)
        self._persist()
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
            self._mark("idempotency", slot)
            self._persist()
            return status, body

    # ------------------------------------------------------------------ dossiers

    def start_dossier(self, domain: str) -> tuple[int, dict]:
        """POST /dossiers: create and build, or report the existing dossier. Call under ``idempotent``."""
        with self._lock:
            dossier = self._dossiers.get(domain)
            if dossier is not None:
                return 200, self._summary(dossier)
            dossier = self._create_dossier(domain)
            self._start_build(dossier)
            return 202, self._summary(dossier)

    def _create_dossier(self, domain: str) -> Dossier:
        self._dossier_counter += 1
        dossier = Dossier(f"d_{self._dossier_counter}", domain)
        self._dossiers[domain] = dossier
        self._mark("dossier", domain)
        return dossier

    def start_batch(self, user_id: str, domains: list[str], budget_units: int) -> tuple[int, dict]:
        """POST /batches: a first build for each domain that has no dossier, all under one budget."""
        with self._lock:
            self._batch_counter += 1
            batch = Batch(f"b_{self._batch_counter}", user_id, budget_units, domains)
            self._batches[batch.batch_id] = batch
            self._mark("batch", batch.batch_id)
            for domain in domains:
                if domain not in self._dossiers:
                    batch.builds.append(domain)
                    self._start_build(self._create_dossier(domain), batch)
            return 202, self._batch_view(batch)

    def get_batch(self, user_id: str, batch_id: str) -> dict:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None or batch.user_id != user_id:
                raise ApiError(404, "not_found", "no such batch")
            return self._batch_view(batch)

    def _batch_view(self, batch: Batch) -> dict:
        running = any(self._dossiers[d].build is not None and self._dossiers[d].build.batch_id == batch.batch_id
                      for d in batch.builds)
        return {"batch_id": batch.batch_id, "state": "running" if running else "done",
                "budget_units": batch.budget_units, "spent_units": batch.spent_units,
                "dossiers": [{"domain": d, "state": self._dossiers[d].state} for d in batch.domains]}

    def refresh_dossier(self, domain: str) -> tuple[int, dict]:
        """POST /dossiers/{domain}/refresh. Call under ``idempotent``."""
        with self._lock:
            dossier = self._dossiers.get(domain)
            if dossier is None:
                raise ApiError(404, "not_found", "no dossier for this domain")
            if dossier.build is None:
                self._start_build(dossier)
            return 202, self._summary(dossier)

    def get_dossier(self, domain: str, as_of: datetime | None = None) -> dict:
        """The dossier now, or as the service had it at ``as_of``."""
        with self._lock:
            dossier = self._existing(domain)
            if as_of is None:
                return {
                    **self._summary(dossier),
                    "researched_at": iso(dossier.researched_at),
                    "spent_units": dossier.spent_units,
                    "fields": copy.deepcopy(dossier.fields),
                }
            found = dossier.snapshot_at(as_of)
            if found is None:
                raise ApiError(404, "not_found", "no build of this dossier completed by then")
            record, spent = found
            return {"dossier_id": dossier.dossier_id, "domain": dossier.domain, "state": "ready",
                    "researched_at": record.time.isoformat(), "spent_units": spent,
                    "fields": copy.deepcopy(record.fields)}

    def values_at(self, domain: str, true_at: str, as_of: datetime | None, as_of_text: str | None) -> dict:
        """What the evidence known at ``as_of`` says each field held on the date ``true_at``."""
        with self._lock:
            dossier = self._existing(domain)
            moment = as_of if as_of is not None else self.clock.now()
            fields = dossier.values_at(true_at, moment)
            if fields is None:
                raise ApiError(404, "not_found", "no build of this dossier completed by then")
            return {"domain": dossier.domain, "true_at": true_at,
                    "as_of": as_of_text if as_of_text is not None else moment.isoformat(), "fields": fields}

    def history(self, domain: str) -> dict:
        with self._lock:
            dossier = self._existing(domain)
            return {"domain": dossier.domain,
                    "fields": {name: copy.deepcopy(dossier.history[name]) for name in ALL_FIELDS}}

    def changes(self, since: int, limit: int) -> dict:
        with self._lock:
            start = bisect_right(self._feed, since, key=lambda entry: entry["seq"])
            page = self._feed[start:start + limit]
            return {"changes": copy.deepcopy(page), "has_more": start + len(page) < len(self._feed)}

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
                    "researched_at": iso(d.researched_at),
                    "spent_units": d.spent_units,
                } for d in page],
                "has_more": offset + len(page) < len(matching),
            }

    def _existing(self, domain: str) -> Dossier:
        dossier = self._dossiers.get(domain)
        if dossier is None:
            raise ApiError(404, "not_found", "no dossier for this domain")
        return dossier

    @staticmethod
    def _summary(dossier: Dossier) -> dict:
        return {"dossier_id": dossier.dossier_id, "domain": dossier.domain, "state": dossier.state}

    # ------------------------------------------------------------------ builds

    def _start_build(self, dossier: Dossier, batch: Batch | None = None) -> None:
        build = Build(self._epoch, self.clock.now(), batch.batch_id if batch is not None else None)
        dossier.build = build
        dossier.spent_before_build = dossier.spent_units
        dossier.inflight = 0
        threading.Thread(target=self._run_build, args=(dossier, build), daemon=True,
                         name=f"build-{dossier.domain}").start()

    def _current(self, dossier: Dossier, build: Build) -> bool:
        return build.epoch == self._epoch and dossier.build is build

    def _run_build(self, dossier: Dossier, build: Build) -> None:
        result: BuildResult | None = None
        try:
            result = self._build_fn(dossier.domain, self._ledger(dossier, build),
                                    lambda: not self._is_current(dossier, build))
        except Exception:   # noqa: BLE001 - a crashed build must still end, as failed
            log.exception("build of %s crashed", dossier.domain)
        with self._lock:
            if not self._current(dossier, build):
                return
            dossier.build = None
            dossier.inflight = 0
            spent = dossier.spent_units - dossier.spent_before_build
            try:
                if result is None or not result.succeeded:
                    raise _BuildFailed()
                entries = dossier.complete_build(build.time, spent, result.pages)
            except _BuildFailed:
                dossier.complete_failed_build(build.time, spent)
            except Exception:   # noqa: BLE001 - nothing of a build that could not be recorded is kept
                log.exception("could not record the build of %s", dossier.domain)
                dossier.complete_failed_build(build.time, spent)
            else:
                for entry in entries:
                    self._feed.append({"seq": self._next_seq, "domain": dossier.domain, **entry})
                    self._next_seq += 1
            self._mark("dossier", dossier.domain)
            if build.batch_id in self._batches:
                self._mark("batch", build.batch_id)
            self._persist()

    def _is_current(self, dossier: Dossier, build: Build) -> bool:
        with self._lock:
            return self._current(dossier, build)

    # ------------------------------------------------------------------ the units a build spends

    def _ledger(self, dossier: Dossier, build: Build) -> Ledger:
        return Ledger(lambda cost: self._reserve(dossier, build, cost),
                      lambda cost, charged: self._settle(dossier, build, cost, charged),
                      lambda: self._remaining(dossier, build))

    def _remaining(self, dossier: Dossier, build: Build) -> int:
        """Units the build may still reserve: under its own 80 and, in a batch, under what the batch has left."""
        with self._lock:
            if not self._current(dossier, build):
                return 0
            left = BUILD_BUDGET_UNITS - (dossier.spent_units - dossier.spent_before_build) - dossier.inflight
            batch = self._batches.get(build.batch_id)
            if batch is not None:
                left = min(left, batch.budget_units - batch.spent_units - batch.inflight)
            return max(left, 0)

    def _reserve(self, dossier: Dossier, build: Build, cost: int) -> None:
        """Count ``cost`` units as in flight before the call is made, so that a stop cannot lose them."""
        with self._lock:
            if self._remaining(dossier, build) < cost:
                raise BudgetExhausted()
            dossier.inflight += cost
            batch = self._batches.get(build.batch_id)
            if batch is not None:
                batch.inflight += cost
            self._log_progress(dossier)

    def _settle(self, dossier: Dossier, build: Build, cost: int, charged: bool) -> None:
        with self._lock:
            if not self._current(dossier, build):
                return
            dossier.inflight -= cost
            batch = self._batches.get(build.batch_id)
            if batch is not None:
                batch.inflight -= cost
            if charged:
                dossier.spent_units += cost
                if batch is not None:
                    batch.spent_units += cost
            self._log_progress(dossier)

    def _log_progress(self, dossier: Dossier) -> None:
        """Journal what the running build has spent and has in flight; it is not forced to disk (see ``Journal.append``)."""
        self._mark("progress", dossier.domain)
        self._persist(sync=False)

    # ------------------------------------------------------------------ export / import

    def export_state(self, journal: bool = False) -> dict:
        """A deep, atomic snapshot. A running build is not in it: the dossier is as it was before.

        ``journal`` gives the form the journal's snapshot takes, which also records the running builds.
        """
        with self._lock:
            state = {
                "users": copy.deepcopy(list(self._users.values())),
                "tokens": dict(self._tokens),
                "dossiers": [export_dossier(d, running=journal)
                             for d in sorted(self._dossiers.values(), key=lambda d: d.domain)],
                "idempotency": [_idempotency_entry(slot, record) for slot, record in self._idempotency.items()],
                "dossier_counter": self._dossier_counter,
                "feed": copy.deepcopy(self._feed),
                "next_seq": self._next_seq,
                "batches": [export_batch(b, None if journal else self._exported_spent(b), journal)
                            for b in self._batches.values()],
                "batch_counter": self._batch_counter,
            }
            return {"track": EXPORT_TRACK, "format_version": EXPORT_VERSION, "state": state}

    def _exported_spent(self, batch: Batch) -> int:
        """What the batch spent, less what its running builds have spent: an export holds their dossiers as before."""
        running = sum(self._dossiers[d].spent_units - self._dossiers[d].spent_before_build
                      for d in batch.builds if self._dossiers[d].build is not None
                      and self._dossiers[d].build.batch_id == batch.batch_id)
        return batch.spent_units - running

    def import_state(self, document: dict) -> None:
        """Replace every piece of state with an export; invalid input changes nothing."""
        if document.get("track") != EXPORT_TRACK or not is_int(document.get("format_version")) \
                or document["format_version"] != EXPORT_VERSION:
            raise validation_failed("not a dossier export of format version 1")
        state = document.get("state")
        if not isinstance(state, dict):
            raise validation_failed("state must be an object")
        try:
            parsed = _parse_state(copy.deepcopy(state))
        except (KeyError, TypeError, ValueError, AttributeError, ApiError) as error:
            raise validation_failed(f"invalid state: {error}") from None
        with self._lock:
            self._adopt(parsed)
            self._full = True
            self._persist()


def _idempotency_entry(slot: tuple, record: IdempotencyRecord) -> dict:
    user_id, method, path, key = slot
    return {"user_id": user_id, "method": method, "path": path, "key": key, "fingerprint": record.fingerprint,
            "status": record.status, "body": copy.deepcopy(record.body)}


# ---------------------------------------------------------------------- parsing helpers

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




def _parse_state(state: dict) -> State:
    """The state of an export: a stage-3 or stage-4 export (it holds the feed), or one of stage 1 or 2, which is upgraded."""
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
    stage_three = "feed" in state
    dossiers: dict[str, Dossier] = {}
    ids = set()
    for raw in state["dossiers"]:
        dossier = parse_dossier(raw) if stage_three else upgrade_dossier(raw)
        if dossier.domain in dossiers or dossier.dossier_id in ids:
            raise ValueError("bad dossier")
        ids.add(dossier.dossier_id)
        dossiers[dossier.domain] = dossier
    idempotency = {}
    for raw in state["idempotency"]:
        slot, record = _parse_idempotency(raw)
        idempotency[slot] = record
    counter = state["dossier_counter"]
    if not is_int(counter) or counter < 0:
        raise ValueError("bad counter")
    batches = {}
    for raw in state.get("batches", []):
        batch = parse_batch(raw)
        if batch.batch_id in batches or any(d not in dossiers for d in batch.builds):
            raise ValueError("bad batch")
        batches[batch.batch_id] = batch
    batch_counter = state.get("batch_counter", 0)
    if not is_int(batch_counter) or batch_counter < len(batches):
        raise ValueError("bad batch counter")
    feed, next_seq = [], 1
    if stage_three:
        feed = [parse_feed_entry(e) for e in state["feed"]]
        next_seq = state["next_seq"]
        seqs = [e["seq"] for e in feed]
        if seqs != sorted(set(seqs)) or not is_int(next_seq) or next_seq <= (seqs[-1] if seqs else 0):
            raise ValueError("bad feed")
    return State(users, dict(tokens), dossiers, idempotency, counter, feed, next_seq, batches, batch_counter)


def _parse_idempotency(raw: dict) -> tuple[tuple, IdempotencyRecord]:
    slot = tuple(raw[k] for k in ("user_id", "method", "path", "key"))
    if not all(isinstance(v, str) for v in slot) or not isinstance(raw["body"], dict) \
            or not isinstance(raw["fingerprint"], str) or not is_int(raw["status"]):
        raise ValueError("bad idempotency record")
    return slot, IdempotencyRecord(raw["fingerprint"], raw["status"], raw["body"])


def _apply_record(state: State, kind: str, payload, clock: str | None) -> str | None:
    """Apply one journal record to ``state``; the clock reading it leaves."""
    if kind == "user":
        state.users[payload["id"]] = payload
    elif kind == "token":
        state.tokens[payload[0]] = payload[1]
    elif kind == "dossier":
        dossier = parse_dossier(payload)
        state.dossiers[dossier.domain] = dossier
    elif kind == "idempotency":
        slot, record = _parse_idempotency(payload)
        state.idempotency[slot] = record
    elif kind == "feed":
        state.feed.extend(payload)
    elif kind == "batch":
        batch = parse_batch(payload)
        state.batches[batch.batch_id] = batch
    elif kind == "progress":
        dossier = state.dossiers[payload["domain"]]
        if dossier.interrupted is not None:
            dossier.interrupted.update(spent=payload["spent"], inflight=payload["inflight"])
        if payload["batch"] in state.batches:
            state.batches[payload["batch"]].spent_units = payload["batch_spent"]
            state.batches[payload["batch"]].inflight = payload["batch_inflight"]
    elif kind == "meta":
        state.counter, state.next_seq = payload["dossier_counter"], payload["next_seq"]
        state.batch_counter = payload.get("batch_counter", state.batch_counter)
        clock = payload["clock"]
    else:
        raise ValueError(f"unknown journal record {kind}")
    return clock
