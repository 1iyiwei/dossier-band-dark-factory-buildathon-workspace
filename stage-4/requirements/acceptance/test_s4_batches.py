"""Stage 4: `POST /batches` and `GET /batches/{id}`: validation, idempotency, ownership, shared budget, spending, concurrency.
IDs (S4-*) in docstrings refer to ../LEDGER.md. Needs the mock web; companies: fleet-*.test and the stage-1 companies."""
import json
import threading
import time
from types import SimpleNamespace

import pytest

import oracle as o
from conftest import (ADA, BASE, BOB, Api, RFC3339, assert_status, check_build, check_citations, check_shape, err,
                      fixture, new_key, ok_json, pmap)
from test_builds import cost_of

FLEET = [f"fleet-{n}.test" for n in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")]
BATCH_KEYS = {"batch_id", "state", "budget_units", "spent_units", "dossiers"}


def post_batch(api, domains, budget, key=None, **kw):
    return api.post("/batches", body={"domains": domains, "budget_units": budget}, key=key or new_key(), **kw)


def get_batch(api, bid):
    return api.get(f"/batches/{bid}")


def wait_batch(api, bid, timeout=90):
    t0 = time.time()
    while True:
        b = ok_json(get_batch(api, bid))
        if b["state"] == "done":
            return b
        assert b["state"] == "running", b
        assert time.time() - t0 < timeout, f"batch still running after {timeout}s: {b}"
        time.sleep(0.2)


def check_batch_shape(b, domains=None, budget=None):
    assert set(b) >= BATCH_KEYS, sorted(b)
    assert isinstance(b["batch_id"], str) and 1 <= len(b["batch_id"]) <= 64
    assert b["state"] in ("running", "done")
    assert isinstance(b["budget_units"], int) and isinstance(b["spent_units"], int) and not isinstance(b["spent_units"], bool)
    assert 0 <= b["spent_units"] <= b["budget_units"], f"S4-OP-5 spent {b['spent_units']} of {b['budget_units']}"
    assert isinstance(b["dossiers"], list)
    for d in b["dossiers"]:
        assert set(d) >= {"domain", "state"} and d["state"] in ("building", "ready", "failed"), d
    if domains is not None:
        assert [d["domain"] for d in b["dossiers"]] == domains
    if budget is not None:
        assert b["budget_units"] == budget


def run_batch(w, domains, budget, timeout=90, api=None):
    api = api or w.ada
    mark = len(w.mock.log())
    first = ok_json(post_batch(api, domains, budget), 202)
    done = wait_batch(api, first["batch_id"], timeout)
    time.sleep(0.3)                      # a call in flight at the end of the last build is logged by now
    return SimpleNamespace(first=first, done=done, calls=w.mock.log()[mark:], api=api)


# --------------------------------------------------------------------------- the happy path
def test_a_batch_researches_new_domains_and_reports_its_shared_budget(pworld):
    """S4-BA-1 S4-BA-4 S4-BA-5 S4-BA-6 S4-BA-8 S4-OP-5 (202 with the batch; dossiers in the order given, normalised, each
    `building`; every dossier built (stage-1 to stage-3 rules); `spent_units` = the cost of the providers' calls = the sum of
    the dossiers' own `spent_units`, at most 80 each and never above the budget)"""
    w = pworld
    domains = ["WWW.Fleet-Alpha.TEST.", " fleet-bravo.test", "fleet-charlie.test"]
    norm = ["fleet-alpha.test", "fleet-bravo.test", "fleet-charlie.test"]
    r = run_batch(w, domains, 300)
    check_batch_shape(r.first, norm, 300)
    assert r.first["state"] == "running" and r.first["spent_units"] == 0
    assert [d["state"] for d in r.first["dossiers"]] == ["building"] * 3
    done = r.done
    check_batch_shape(done, norm, 300)
    assert done["batch_id"] == r.first["batch_id"] and done["state"] == "done"
    assert [d["state"] for d in done["dossiers"]] == ["ready"] * 3
    bodies = {d: w.dossier(w.ada, d) for d in norm}
    for d, b in bodies.items():
        assert b["state"] == "ready" and b["spent_units"] <= 80
        check_build(b, w.mock.log())
    assert done["spent_units"] == cost_of(r.calls) == sum(b["spent_units"] for b in bodies.values()) > 0
    listed = {x["domain"]: x for x in ok_json(w.ada.get("/dossiers"))["dossiers"]}
    assert set(norm) <= set(listed)
    # reading the batch makes no provider call and does not change it
    n = len(w.mock.log())
    assert ok_json(get_batch(w.ada, done["batch_id"])) == done
    assert len(w.mock.log()) == n


def test_a_domain_with_a_dossier_is_not_researched_and_costs_the_batch_nothing(pworld):
    """S4-BA-5 S4-BA-4 S4-BA-6 (northwind has a dossier: the batch lists its state, makes no call for it and its dossier is
    untouched; the new domain is researched)"""
    w = pworld
    old, _ = w.build(w.ada, "northwind-optics.test")
    mark = len(w.mock.log())
    r = run_batch(w, ["northwind-optics.test", "fleet-delta.test"], 100)
    assert [d["domain"] for d in r.first["dossiers"]] == ["northwind-optics.test", "fleet-delta.test"]
    assert [d["state"] for d in r.first["dossiers"]] == ["ready", "building"]
    assert w.dossier(w.ada, "northwind-optics.test") == old
    for c in r.calls:
        assert "northwind" not in (c["query"] or "").lower() and not any("northwind" in u for u in c["urls"]), c
    assert r.done["spent_units"] == cost_of(r.calls) == w.dossier(w.ada, "fleet-delta.test")["spent_units"] > 0
    assert [d["state"] for d in r.done["dossiers"]] == ["ready", "ready"]


def test_a_batch_of_known_domains_has_no_builds_and_is_done(pworld):
    """S4-BA-5 S4-BA-8 (every domain has a dossier: nothing is researched, spent 0, no provider call)"""
    w = pworld
    w.build(w.ada, "northwind-optics.test")
    n = len(w.mock.log())
    j = ok_json(post_batch(w.ada, ["northwind-optics.test"], 50), 202)
    check_batch_shape(j, ["northwind-optics.test"], 50)
    assert j["state"] == "done" and j["spent_units"] == 0 and j["dossiers"][0]["state"] == "ready"
    assert len(w.mock.log()) == n
    assert ok_json(get_batch(w.ada, j["batch_id"])) == j


def test_a_dossier_refreshed_later_does_not_change_the_batch_total(pworld):
    """S4-BA-6 (`spent_units` is the cost of the calls the batch's builds made, not of later refreshes)"""
    w = pworld
    r = run_batch(w, FLEET[:2], 200)
    w.refresh(w.ada, FLEET[0])
    assert ok_json(get_batch(w.ada, r.first["batch_id"]))["spent_units"] == r.done["spent_units"]


def test_the_batch_is_running_until_its_builds_end_and_spending_only_grows(pworld):
    """S4-BA-8 S4-BA-6 (running while any of its builds runs, then done; `spent_units` never decreases nor exceeds the budget)"""
    w = pworld
    w.mock.fault("nimble", ["search"], "delay", seconds=1)
    j = ok_json(post_batch(w.ada, FLEET[:3], 150), 202)
    seen, t0 = [], time.time()
    while True:
        b = ok_json(get_batch(w.ada, j["batch_id"]))
        check_batch_shape(b, FLEET[:3], 150)
        seen.append(b)
        if b["state"] == "done":
            break
        assert any(d["state"] == "building" for d in b["dossiers"]) or time.time() - t0 < 2, \
            "running while some build runs"
        assert time.time() - t0 < 60
        time.sleep(0.1)
    assert seen[0]["state"] == "running" and len(seen) > 2
    sp = [b["spent_units"] for b in seen]
    assert sp == sorted(sp)
    assert all(d["state"] != "building" for d in seen[-1]["dossiers"])


# --------------------------------------------------------------------------- budget
def test_a_budget_of_one_unit_is_never_exceeded(pworld):
    """S4-BA-7 S4-OP-5 S4-BA-6 (the batch makes no call that would take it above 1 unit; its builds complete; spent = cost)"""
    w = pworld
    r = run_batch(w, FLEET[:3], 1, timeout=60)
    assert r.done["state"] == "done" and r.done["spent_units"] <= 1
    assert cost_of(r.calls) <= 1 and r.done["spent_units"] == cost_of(r.calls)
    for d in FLEET[:3]:
        b = w.dossier(w.ada, d)
        assert b["state"] in ("ready", "failed")
        check_shape(b)
        check_citations(b, w.mock.log())
        assert b["spent_units"] <= 1


@pytest.mark.parametrize("budget", [25, 60])
def test_the_budget_is_shared_by_the_builds_and_never_exceeded(pworld, budget):
    """S4-BA-7 S4-OP-5 S4-BA-6 (six builds in parallel on one budget: the providers billed at most `budget`; spent_units is
    exactly what the providers billed; the remaining builds complete with what they obtained: every citation is served
    text, a field is known only on evidence, and one that a fully served page supports is known)"""
    w = pworld
    r = run_batch(w, FLEET, budget, timeout=120)
    billed = cost_of(r.calls)
    assert billed <= budget, f"S4-OP-5 the providers billed {billed} > {budget}"
    assert r.done["spent_units"] == billed and r.done["state"] == "done"
    bodies = {d: w.dossier(w.ada, d) for d in FLEET}
    assert sum(b["spent_units"] for b in bodies.values()) == billed
    for d, b in bodies.items():
        assert b["state"] in ("ready", "failed"), (d, b["state"])
        check_shape(b)
        check_citations(b, w.mock.log())
        if b["state"] == "failed":
            assert b["researched_at"] is None
        else:
            full = [s["text"] for c in r.calls if c["status"] < 400 and (c["method"] == "extract" or
                    (c["method"] == "search" and c["depth"] == "deep")) for s in c["served"]]
            for name in ("hq_city", "ceo"):
                if o.sentence_values(full, name, d):
                    assert b["fields"][name]["status"] != "unknown", \
                        f"{d} {name}: a page the build obtained supports a value, the field must be known"
    assert billed >= min(budget, 10), "the batch should have spent something"


def test_a_large_budget_does_not_lift_the_per_build_limit(pworld):
    """S4-BA-6 S4-OP-5 (budget 100000: every build still spends at most 80 units and its cost counts in its dossier)"""
    w = pworld
    r = run_batch(w, FLEET + ["tidewell-pharma.test", "kestrel-freight.test"], 100000, timeout=120)
    for d in FLEET + ["tidewell-pharma.test", "kestrel-freight.test"]:
        b = w.dossier(w.ada, d)
        assert b["state"] == "ready" and b["spent_units"] <= 80
    assert r.done["spent_units"] == cost_of(r.calls) == sum(
        w.dossier(w.ada, d)["spent_units"] for d in FLEET + ["tidewell-pharma.test", "kestrel-freight.test"])


def test_twelve_parallel_builds_cannot_overspend_a_small_budget(pworld):
    """S4-OP-5 S4-BA-7 (concurrency: twelve builds, budget 100: the providers billed at most 100)"""
    w = pworld
    doms = FLEET + ["northwind-optics.test", "tidewell-pharma.test", "kestrel-freight.test", "quillstone-bio.test",
                    "orchard-lane-foods.test", "bluefin-marine.test"]
    r = run_batch(w, doms, 100, timeout=150)
    assert cost_of(r.calls) <= 100 and r.done["spent_units"] == cost_of(r.calls)
    assert r.done["state"] == "done" and all(d["state"] in ("ready", "failed") for d in r.done["dossiers"])


# --------------------------------------------------------------------------- validation
def bad(w, body, status=422, code="validation_failed"):
    r = w.ada.post("/batches", body=body, key=new_key())
    err(r, status, code)


def test_the_request_is_validated(pworld):
    """S4-BA-3 (domains missing, empty or longer than 50: 422; an invalid entry; two entries the same after normalisation;
    budget_units missing, not an integer, below 1 or above 100000: 422)"""
    w = pworld
    n = len(w.mock.log())
    ok = ["fleet-alpha.test"]
    bad(w, {"budget_units": 10})
    bad(w, {"domains": [], "budget_units": 10})
    bad(w, {"domains": [f"zz{i:02d}.test" for i in range(51)], "budget_units": 10})
    for entry in ("https://acme.test", "acme", "a_b.test", "-a.test", "", "acme.test/path", "x" * 64 + ".test", "www.test"):
        bad(w, {"domains": ["fleet-bravo.test", entry], "budget_units": 10})
    bad(w, {"domains": ["fleet-alpha.test", "WWW.Fleet-Alpha.TEST."], "budget_units": 10})
    bad(w, {"domains": ["a.test", "b.test", "a.test"], "budget_units": 10})
    bad(w, {"domains": ok})
    for budget in (0, -1, 100001, 10**9):
        bad(w, {"domains": ok, "budget_units": budget})
    assert len(w.mock.log()) == n, "a refused request makes no provider call"
    assert ok_json(w.ada.get("/dossiers"))["dossiers"] == [], "a refused request creates nothing"


@pytest.mark.parametrize("budget", ["10", True, False, 1.5, None, [10], {"v": 10}, 10.5, "1e2"])
def test_a_budget_that_is_not_an_integer_is_422_whatever_its_json_type(pworld, budget):
    """S4-BA-3 (a string, `true` or `1.5` included: 422 `validation_failed`, not 400 `malformed_request`)"""
    bad(pworld, {"domains": ["fleet-alpha.test"], "budget_units": budget})


def test_the_limits_are_valid_values(pworld):
    """S4-BA-3 (budget 1 and 100000; 50 domains; the 50th entry is accepted)"""
    w = pworld
    assert_status(post_batch(w.ada, ["fleet-alpha.test"], 1), 202)
    assert_status(post_batch(w.ada, ["fleet-bravo.test"], 100000), 202)


def test_fifty_domains_are_accepted_at_once_and_all_researched(pworld):
    """S4-BA-3 S4-BA-4 S4-BA-5 S4-BA-8 S4-OP-5 (50 entries: 202 within the 5 s request timeout, dossiers in order; the 51st
    is refused; the batch ends `done`; no build above 80 units; the batch spent exactly what the providers billed)"""
    w = pworld
    doms = [f"zz-batch-{i:02d}.test" for i in range(50)]
    mark = len(w.mock.log())
    j = ok_json(post_batch(w.ada, doms, 100000), 202)
    check_batch_shape(j, doms, 100000)
    assert len(j["dossiers"]) == 50
    done = wait_batch(w.ada, j["batch_id"], 300)
    time.sleep(0.5)
    calls = w.mock.log()[mark:]
    assert done["spent_units"] == cost_of(calls)
    listed = {x["domain"]: x for x in ok_json(w.ada.get("/dossiers", params={"limit": 200}))["dossiers"]}
    assert set(doms) <= set(listed) and all(listed[d]["state"] in ("ready", "failed") for d in doms)
    assert all(listed[d]["spent_units"] <= 80 for d in doms)
    assert sum(listed[d]["spent_units"] for d in doms) == done["spent_units"]
    bad(w, {"domains": doms + ["zz-batch-50.test"], "budget_units": 10})


# --------------------------------------------------------------------------- idempotency, auth, ownership
def test_the_idempotency_key_rules_apply_to_batches(pworld):
    """S4-BA-2 S4-WP-1 (missing or empty key 400; 256 characters 422; a replay is 200 with the original body, also after the
    batch is done, and makes no call; same key another body 409, also for an invalid body; a key whose request failed with
    4xx is a first use; unknown body fields do not matter; users have their own keys)"""
    w = pworld
    body = {"domains": ["fleet-alpha.test", "fleet-bravo.test"], "budget_units": 120}
    err(w.ada.post("/batches", body=body), 400, "missing_idempotency_key")
    err(w.ada.post("/batches", body=body, headers={"Idempotency-Key": ""}), 400, "missing_idempotency_key")
    err(w.ada.post("/batches", body=body, key="k" * 256), 422, "validation_failed")
    assert_status(post_batch(w.ada, body["domains"], 120, key="k" * 255), 202)
    w.reset()
    k = new_key()
    first = ok_json(w.ada.post("/batches", body=body, key=k), 202)
    wait_batch(w.ada, first["batch_id"])
    n = len(w.mock.log())
    assert ok_json(w.ada.post("/batches", body=dict(body, extra={"x": 1}), key=k), 200) == first
    assert ok_json(w.ada.post("/batches", body={"budget_units": 120, "domains": body["domains"]}, key=k), 200) == first
    assert len(w.mock.log()) == n
    err(w.ada.post("/batches", body=dict(body, budget_units=121), key=k), 409, "idempotency_key_reuse")
    err(w.ada.post("/batches", body={"domains": [], "budget_units": 120}, key=k), 409, "idempotency_key_reuse")
    err(w.ada.post("/batches", body={"domains": ["fleet-charlie.test"], "budget_units": 120}, key=k), 409, "idempotency_key_reuse")
    k2 = new_key()
    err(w.ada.post("/batches", body={"domains": [], "budget_units": 5}, key=k2), 422, "validation_failed")
    again = ok_json(w.ada.post("/batches", body={"domains": ["fleet-delta.test"], "budget_units": 60}, key=k2), 202)
    assert again["batch_id"] != first["batch_id"]
    other = ok_json(w.bob.post("/batches", body={"domains": ["fleet-echo.test"], "budget_units": 60}, key=k), 202)
    assert other["batch_id"] not in (first["batch_id"], again["batch_id"])
    # a different path with the same key is not a replay
    assert_status(w.ada.post("/dossiers", body={"domain": "fleet-foxtrot.test"}, key=k), 202)


def test_concurrent_identical_batch_requests_run_one_batch(pworld):
    """S4-BA-2 S4-WP-2 (twelve identical requests with one unused key: exactly one 202 and the others 200 with the same body;
    one batch, one build per domain)"""
    w = pworld
    body = {"domains": FLEET[:2], "budget_units": 150}
    k = new_key()
    mark = len(w.mock.log())
    rs = pmap(lambda _: w.ada.post("/batches", body=body, key=k), range(12), workers=12)
    codes = sorted(r.status_code for r in rs)
    assert codes == [200] * 11 + [202], codes
    assert len({json.dumps(r.json(), sort_keys=True) for r in rs}) == 1
    first = next(r for r in rs if r.status_code == 202).json()
    done = wait_batch(w.ada, first["batch_id"])
    time.sleep(0.3)
    calls = w.mock.log()[mark:]
    assert done["spent_units"] == cost_of(calls) <= 150
    assert sum(1 for c in calls if c["method"] == "search" and c["query"] == FLEET[0] and c["status"] < 400) == 1, \
        "one build per domain"


def test_concurrent_batches_and_requests_for_one_domain_make_one_dossier_and_one_build(pworld):
    """S4-BA-5 S4-BA-11 (two batches and a POST /dossiers racing for the same new domain: one dossier, one build; the domain
    is researched by exactly one of them and costs only that one; nothing is billed twice)"""
    w = pworld
    mark = len(w.mock.log())

    def go(i):
        if i == 0:
            return w.ada.post("/dossiers", body={"domain": "fleet-echo.test"}, key=new_key())
        return w.ada.post("/batches", body={"domains": ["fleet-echo.test", f"zz-race-{i}.test"], "budget_units": 200},
                          key=new_key())
    rs = pmap(go, range(3), workers=3)
    assert all(r.status_code in (200, 202) for r in rs), [(r.status_code, r.text[:100]) for r in rs]
    batches = [r.json() for r in rs[1:]]
    for b in batches:
        wait_batch(w.ada, b["batch_id"])
    w.wait(w.ada, "fleet-echo.test", 60)
    time.sleep(0.5)
    calls = w.mock.log()[mark:]
    assert sum(1 for c in calls if c["method"] == "search" and c["query"] == "fleet-echo.test" and c["status"] < 400) == 1
    final = [ok_json(get_batch(w.ada, b["batch_id"])) for b in batches]
    echo = w.dossier(w.ada, "fleet-echo.test")["spent_units"]
    own = [w.dossier(w.ada, f"zz-race-{i}.test")["spent_units"] for i in (1, 2)]
    total = sum(f["spent_units"] for f in final)
    assert total <= sum(own) + echo and total >= sum(own), "the shared domain costs at most the batch that created it"
    assert cost_of(calls) == echo + sum(own)


def test_batches_need_a_token_and_belong_to_their_creator(pworld):
    """S4-BA-9 S4-BA-12 (401 without a valid token, also for a missing key; another user's batch is 404 `not_found`, so is an
    unknown id; the dossiers stay visible to everyone)"""
    w = pworld
    body = {"domains": ["fleet-alpha.test"], "budget_units": 100}
    err(w.anon.post("/batches", body=body, key=new_key()), 401, "unauthenticated")
    err(w.anon.post("/batches", body=body), 401, "unauthenticated")
    err(w.anon.post("/batches", body=body, token="nope"), 401, "unauthenticated")
    err(w.anon.get("/batches/b_1"), 401, "unauthenticated")
    j = ok_json(w.ada.post("/batches", body=body, key=new_key()), 202)
    err(get_batch(w.bob, j["batch_id"]), 404, "not_found")
    err(get_batch(w.ada, "b_does-not-exist"), 404, "not_found")
    err(get_batch(w.ada, "9" * 40), 404, "not_found")
    done = wait_batch(w.ada, j["batch_id"])
    err(get_batch(w.bob, j["batch_id"]), 404, "not_found")
    assert [x["domain"] for x in ok_json(w.bob.get("/dossiers"))["dossiers"]] == ["fleet-alpha.test"]
    assert ok_json(get_batch(w.ada, j["batch_id"])) == done


def test_batch_endpoints_are_json_with_the_error_envelope(pworld):
    """S4-BA-1 S4-BA-8 (application/json; charset=utf-8; a body that does not parse is 400 `malformed_request`; `domains` that
    is not an array is refused with 400 or 422)"""
    w = pworld
    r = w.ada.post("/batches", raw="{not json", key=new_key())
    err(r, 400, "malformed_request")
    for body in ({"domains": "fleet-alpha.test", "budget_units": 10}, {"domains": [1, 2], "budget_units": 10},
                 {"domains": None, "budget_units": 10}):
        r = w.ada.post("/batches", body=body, key=new_key())
        assert r.status_code in (400, 422), (body, r.status_code)
        assert r.json()["error"]["code"] in ("malformed_request", "validation_failed")
    err(w.ada.post("/batches", raw="[1]", key=new_key()), 400, "malformed_request")
