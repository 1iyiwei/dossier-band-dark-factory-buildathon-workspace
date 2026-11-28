"""Shared drivers for the stage-3 tests: the meridian-ledger timeline (six builds, one of them failed,
over five epochs of the mock web), response helpers and the model reduced to what tests compare.

Times of builds are set through POST /_test/clock before each build, the web changes through the mock's
epoch (gen_corpus.py, stage-3 section). Expectations come from s3model.py (stage-3.md alone)."""
from __future__ import annotations

from datetime import timezone
from types import SimpleNamespace
from urllib.parse import quote

import s2model as m
import s3model as s3
from conftest import (BASE, CORPUS_S2, MOCK, MOCK_TOKEN, Mock, World, assert_status, fixture, ok_json,
                      parse_ts, check_build, err)

M = "meridian-ledger.test"
T = {"0": "2026-03-01T09:00:00+00:00", "1": "2026-04-01T09:00:00+00:00", "f": "2026-04-15T09:00:00+00:00",
     "2": "2026-05-01T09:00:00+00:00", "3": "2026-06-01T09:00:00+00:00", "4": "2026-07-01T09:00:00+00:00"}
# (key, epoch of the web, the build is made to fail?)
STEPS = [("0", 0, False), ("1", 1, False), ("f", 1, True), ("2", 2, False), ("3", 3, False), ("4", 4, False)]
SEVEN = s3.ALL


def dt(s):
    return m.parse_rfc3339(s)


def run_timeline(domain=M, steps=STEPS, times=T, check=True):
    """Builds `domain` through the steps on a clean service. Returns a namespace with, per step,
    the snapshot (GET right after the build), the mock calls of the build and the model."""
    mock = Mock(MOCK, MOCK_TOKEN)
    w = World(mock)
    w.reset(fixture(now=times[steps[0][0]]))
    out = SimpleNamespace(w=w, mock=mock, domain=domain, steps=[], builds=[], times=times)
    first = True
    for key, epoch, fail in steps:
        if not first:
            assert_status(w.clock(times[key]), 204)
        mock.epoch(epoch)
        if fail:
            mock.break_all()
        if first:
            body, calls = w.build(w.ada, domain)
        else:
            body, calls = w.refresh(w.ada, domain)
        if fail:
            mock.clear()
        rec = SimpleNamespace(key=key, epoch=epoch, fail=fail, time=dt(times[key]), body=body, calls=calls)
        out.steps.append(rec)
        if not fail:
            out.builds.append(s3.build_from_epoch(domain, epoch, rec.time, CORPUS_S2))
            if check:
                assert body["state"] == "ready", (key, body["state"])
                check_build(body, calls, epoch)
        else:
            assert body["state"] == "failed", (key, body["state"])
        first = False
    out.ready = [s for s in out.steps if not s.fail]
    out.hist, out.feed = s3.history(out.builds)
    return out


def get(api, path, **params):
    return api.get(path, params=params or None)


def history_of(api, domain):
    return ok_json(api.get(f"/dossiers/{domain}/history"))


def changes_all(api, since=0, limit=200):
    """Every feed entry, following has_more."""
    out = []
    while True:
        j = ok_json(api.get("/changes", params={"since": since, "limit": limit}))
        assert set(j) >= {"changes", "has_more"}
        out += j["changes"]
        if not j["has_more"]:
            return out
        assert j["changes"], "has_more with no entries"
        since = j["changes"][-1]["seq"]


def as_of(api, domain, ts):
    return api.get(f"/dossiers/{domain}", params={"as_of": ts})


def values(api, domain, true_at, as_of_ts=None):
    p = {"true_at": true_at}
    if as_of_ts is not None:
        p["as_of"] = as_of_ts
    return api.get(f"/dossiers/{domain}/values", params=p)


def spent_until(tl, when):
    """Total spend of the builds (ready or failed) whose time is at or before `when`."""
    last = None
    for s in tl.steps:
        if s.time <= when:
            last = s
    return last.body["spent_units"] if last else None


def utc_date(ts):
    return dt(ts).astimezone(timezone.utc).date().isoformat()


def full_view(api, domain, times=T, tas=("2025-09-01", "2026-01-01", "2026-03-25", "2026-06-15"), keys=None):
    """Everything a client can read about one dossier, for before/after comparisons (import, restart)."""
    out = {"get": ok_json(api.get(f"/dossiers/{domain}")),
           "list": ok_json(api.get("/dossiers", params={"limit": 200})),
           "hist": history_of(api, domain), "feed": changes_all(api)}
    for k in (times if keys is None else keys):
        r = as_of(api, domain, times[k])
        out[("asof", k)] = (r.status_code, r.json())
        for ta in tas:
            r = values(api, domain, ta, times[k])
            out[("values", k, ta)] = (r.status_code, r.json())
    return out
