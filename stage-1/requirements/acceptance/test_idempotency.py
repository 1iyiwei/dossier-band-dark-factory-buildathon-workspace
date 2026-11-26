"""Idempotency (§7) on POST /dossiers and POST /dossiers/{domain}/refresh. IDs in docstrings."""
import json
import time

import pytest

from conftest import (Api, BASE, assert_status, err, new_key, ok_json, pmap, domain_searches,
                      successful)

D1, D2 = "idem-one.test", "idem-two.test"


def post(api, domain, key, **kw):
    return api.post("/dossiers", body={"domain": domain}, key=key, **kw)


def refresh(api, domain, key, **kw):
    return api.post(f"/dossiers/{domain}/refresh", key=key, **kw)


def test_missing_or_empty_key(world):
    """ID-1"""
    err(world.ada.post("/dossiers", body={"domain": D1}), 400, "missing_idempotency_key")
    err(world.ada.post("/dossiers", body={"domain": D1}, headers={"Idempotency-Key": ""}), 400,
        "missing_idempotency_key")
    assert_status(post(world.ada, D1, new_key()), 202)
    err(world.ada.post(f"/dossiers/{D1}/refresh"), 400, "missing_idempotency_key")
    err(world.ada.post(f"/dossiers/{D1}/refresh", headers={"Idempotency-Key": ""}), 400,
        "missing_idempotency_key")
    assert_status(world.ada.get("/dossiers"), 200)       # a GET needs no key


def test_key_length(world):
    """ID-2"""
    assert_status(post(world.ada, D1, "k" * 255), 202)
    err(post(world.ada, D2, "k" * 256), 422, "validation_failed")
    assert_status(post(world.ada, D2, "k"), 202)
    assert_status(refresh(world.ada, D1, "r" * 255), 202)
    err(refresh(world.ada, D1, "r" * 256), 422, "validation_failed")


def test_replay_is_200_with_the_original_body(world):
    """ID-4 ID-12"""
    k = new_key()
    first = ok_json(post(world.ada, D1, k), 202)
    again = ok_json(post(world.ada, D1, k), 200)
    assert again == first and first["state"] == "building"
    world.wait(world.ada, D1)
    later = ok_json(post(world.ada, D1, k), 200)
    assert later == first, "a replay returns the original response even after the dossier changed"
    # and a replay of a request that was answered 200 (existing dossier)
    k2 = new_key()
    ex = ok_json(post(world.bob, D1, k2), 200)
    assert ex["state"] == "ready"
    assert ok_json(post(world.bob, D1, k2), 200) == ex


def test_replay_of_refresh_returns_the_original_202_body(world):
    """ID-4 ID-12 ID-14"""
    world.request(world.ada, D1)
    world.wait(world.ada, D1)
    k = new_key()
    first = ok_json(refresh(world.ada, D1, k), 202)
    assert first["state"] == "building" and first["domain"] == D1
    world.wait(world.ada, D1)
    again = ok_json(refresh(world.ada, D1, k), 200)
    assert again == first


def test_replay_makes_no_provider_call_and_no_build(pworld):
    """ID-12 BD-6"""
    w = pworld
    k = new_key()
    first = ok_json(post(w.ada, "tidewell-pharma.test", k), 202)
    b = w.wait(w.ada, "tidewell-pharma.test")
    n, spent = len(w.mock.log()), b["spent_units"]
    for _ in range(3):
        assert ok_json(post(w.ada, "tidewell-pharma.test", k), 200) == first
    kr = new_key()
    r1 = ok_json(refresh(w.ada, "tidewell-pharma.test", kr), 202)
    w.wait(w.ada, "tidewell-pharma.test")
    n2 = len(w.mock.log())
    assert n2 > n
    for _ in range(3):
        assert ok_json(refresh(w.ada, "tidewell-pharma.test", kr), 200) == r1
    time.sleep(1)
    assert len(w.mock.log()) == n2
    assert w.dossier(w.ada, "tidewell-pharma.test")["state"] == "ready"


def test_same_key_different_body_is_409(world):
    """ID-5 ID-7"""
    k = new_key()
    assert_status(post(world.ada, D1, k), 202)
    err(post(world.ada, D2, k), 409, "idempotency_key_reuse")
    err(post(world.ada, "Idem-One.test", k), 409, "idempotency_key_reuse")   # different spelling
    err(post(world.ada, "www.idem-one.test", k), 409, "idempotency_key_reuse")
    err(world.ada.post("/dossiers", body={"domain": D2, "x": 1}, key=k), 409,
        "idempotency_key_reuse")
    assert ok_json(post(world.ada, D1, k), 200)["domain"] == D1
    assert ok_json(world.ada.get("/dossiers"))["dossiers"][0]["domain"] == D1
    assert len(ok_json(world.ada.get("/dossiers"))["dossiers"]) == 1


def test_body_equality_is_semantic(world):
    """ID-9"""
    k = new_key()
    h = {"Content-Type": "application/json"}
    first = ok_json(world.ada.post("/dossiers", raw=b'{"domain":"idem-one.test"}', key=k), 202)
    for raw in (b'{ "domain" : "idem-one.test" }', b'{"domain":"idem-one.test","extra":1}',
                b'\n{"extra":{"a":[1,2]},\n "domain":"idem-one.test","zz":null}\n'):
        assert ok_json(world.ada.post("/dossiers", raw=raw, key=k), 200) == first
    # key order of a two-field object, escapes
    k2 = new_key()
    f2 = ok_json(world.ada.post("/dossiers", raw=b'{"domain":"idem-two.test","a":1,"b":2}', key=k2), 202)
    assert ok_json(world.ada.post("/dossiers", raw=b'{"b":3,"a":9,"domain":"idem\\u002dtwo.test"}',
                                  key=k2), 200) == f2


def test_refresh_ignores_any_body(world):
    """ID-10 RF-5"""
    world.request(world.ada, D1)
    world.wait(world.ada, D1)
    k = new_key()
    first = ok_json(world.ada.post(f"/dossiers/{D1}/refresh", key=k), 202)
    assert ok_json(world.ada.post(f"/dossiers/{D1}/refresh", key=k, body={"a": 1}), 200) == first
    assert ok_json(world.ada.post(f"/dossiers/{D1}/refresh", key=k, raw=b"not json at all"),
                   200) == first
    assert ok_json(world.ada.post(f"/dossiers/{D1}/refresh", key=k, raw=b"[1,2,3]"), 200) == first
    world.wait(world.ada, D1)
    k2 = new_key()          # a first use with junk or an array body is fine too
    assert_status(world.ada.post(f"/dossiers/{D1}/refresh", key=k2, raw=b"{{{"), 202)


def test_keys_are_scoped_to_the_user(world):
    """ID-3"""
    k = new_key()
    a = ok_json(post(world.ada, D1, k), 202)
    b = ok_json(post(world.bob, D2, k), 202)               # no interaction with ada's use
    assert b["domain"] == D2 and a["domain"] == D1
    assert ok_json(post(world.ada, D1, k), 200) == a
    assert ok_json(post(world.bob, D2, k), 200) == b
    err(post(world.bob, D1, k), 409, "idempotency_key_reuse")
    world.wait(world.ada, D1)
    world.wait(world.ada, D2)
    kr = new_key()
    assert_status(refresh(world.ada, D1, kr), 202)
    assert_status(refresh(world.bob, D2, kr), 202)         # same key string, other user


def test_same_key_other_path_is_a_different_request(world):
    """ID-6 ID-14"""
    world.request(world.ada, D1)
    world.request(world.ada, D2)
    world.wait(world.ada, D1)
    world.wait(world.ada, D2)
    k = new_key()
    p1 = ok_json(post(world.ada, D1, k), 200)              # existing dossier: 200
    r1 = ok_json(refresh(world.ada, D1, k), 202)           # same key on another path: first use
    assert r1["state"] == "building"
    r2 = ok_json(refresh(world.ada, D2, k), 202)           # same key, other path again
    assert r2["domain"] == D2
    assert ok_json(refresh(world.ada, D1, k), 200) == r1
    assert ok_json(refresh(world.ada, D2, k), 200) == r2
    assert ok_json(post(world.ada, D1, k), 200) == p1


def test_refresh_path_spellings_are_different_requests(world):
    """ID-7"""
    world.request(world.ada, D1)
    world.wait(world.ada, D1)
    k = new_key()
    a = ok_json(refresh(world.ada, "Idem-One.TEST", k), 202)
    b = ok_json(refresh(world.ada, "idem-one.test", k), 202)    # not a replay -> normal 202
    assert a == b                                              # (same running build)
    c = ok_json(refresh(world.ada, "idem-one.test", k), 200)    # now it is a replay
    assert c == b


def test_key_reusable_after_a_4xx(world):
    """ID-8"""
    k = new_key()
    err(post(world.ada, "https://bad", k), 422, "validation_failed")
    assert_status(post(world.ada, D1, k), 202)                 # first use
    k2 = new_key()
    err(refresh(world.ada, D2, k2), 404, "not_found")
    world.request(world.ada, D2)
    world.wait(world.ada, D2)
    r = ok_json(refresh(world.ada, D2, k2), 202)
    assert r["domain"] == D2
    k3 = new_key()
    err(world.ada.post("/dossiers", body={"domain": 5}, key=k3), 400, "malformed_request")
    err(world.ada.post("/dossiers", raw=b"{x", key=k3), 400, "malformed_request")
    assert_status(post(world.ada, "idem-four.test", k3), 202)


def test_claimed_key_is_resolved_before_field_validation(world):
    """ID-13"""
    k = new_key()
    first = ok_json(post(world.ada, D1, k), 202)
    for bad in ({"domain": 123}, {"domain": "https://x.test/a"}, {}, {"domain": None},
                {"domain": ["a.test"]}, {"domain": ""}):
        err(world.ada.post("/dossiers", body=bad, key=k), 409, "idempotency_key_reuse")
    # a body that does not parse as a JSON object is still 400
    err(world.ada.post("/dossiers", raw=b"{broken", key=k), 400, "malformed_request")
    err(world.ada.post("/dossiers", raw=b"[]", key=k), 400, "malformed_request")
    assert ok_json(post(world.ada, D1, k), 200) == first
    # other users' claims do not count
    assert_status(world.bob.post("/dossiers", body={"domain": ""}, key=k), 422)


def test_concurrent_identical_requests(pworld):
    """ID-11 PD-6 CC-2"""
    w = pworld
    w.mock.fault("nimble", ["search"], "delay", 1)
    k = new_key()
    rs = pmap(lambda _: post(w.ada, "tidewell-pharma.test", k), range(16))
    codes = sorted(r.status_code for r in rs)
    assert codes == [200] * 15 + [202], codes
    bodies = {json.dumps(r.json(), sort_keys=True) for r in rs}
    assert len(bodies) == 1, bodies
    w.wait(w.ada, "tidewell-pharma.test")
    time.sleep(1.5)
    calls = w.mock.log()
    assert len(domain_searches(calls, "tidewell-pharma.test")) == 1
    assert len(ok_json(w.ada.get("/dossiers"))["dossiers"]) == 1


def test_concurrent_same_key_with_two_bodies(world):
    """ID-15 CC-2"""
    k = new_key()
    doms = [D1, D2] * 6
    rs = pmap(lambda d: (d, post(world.ada, d, k)), doms)
    wins = [(d, r) for d, r in rs if r.status_code == 202]
    assert len(wins) == 1, [r.status_code for _, r in rs]
    win = wins[0][0]
    for d, r in rs:
        if r.status_code == 202:
            continue
        if d == win:
            assert r.status_code == 200 and r.json() == wins[0][1].json()
        else:
            err(r, 409, "idempotency_key_reuse")
    assert [d["domain"] for d in ok_json(world.ada.get("/dossiers"))["dossiers"]] == [win]


def test_concurrent_same_domain_different_keys_and_spellings(pworld):
    """PD-6 CC-2"""
    w = pworld
    w.mock.fault("nimble", ["search"], "delay", 1)
    spell = ["tidewell-pharma.test", "TIDEWELL-PHARMA.test.", "www.tidewell-pharma.test"]
    rs = pmap(lambda i: post(w.ada if i % 2 else w.bob, spell[i % 3], new_key()), range(18))
    codes = sorted(r.status_code for r in rs)
    assert codes == [200] * 17 + [202], codes
    assert len({r.json()["dossier_id"] for r in rs}) == 1
    w.wait(w.ada, "tidewell-pharma.test")
    time.sleep(1.5)
    assert len(domain_searches(w.mock.log(), "tidewell-pharma.test")) == 1


def test_concurrent_refreshes_start_one_build(pworld):
    """RF-2 CC-2"""
    w = pworld
    w.build(w.ada, "tidewell-pharma.test")
    w.mock.fault("nimble", ["search"], "delay", 2)
    w.mock.fault("tavily", ["search"], "delay", 2)
    mark = len(w.mock.log())
    rs = pmap(lambda i: refresh(w.ada if i % 2 else w.bob, "tidewell-pharma.test", new_key()),
              range(12))
    for r in rs:
        assert_status(r, 202)
    assert len({json.dumps(r.json(), sort_keys=True) for r in rs}) == 1
    assert rs[0].json()["state"] == "building"
    w.wait(w.ada, "tidewell-pharma.test", 40)
    time.sleep(2.5)
    assert len(domain_searches(w.mock.log()[mark:], "tidewell-pharma.test")) == 1
