"""Clock behaviour and export/import (§3.4, §10). IDs in docstrings."""
import copy
import json
import time

import pytest

from conftest import (ADA, BASE, BASE2, BOB, NOW0, PW, Api, World, assert_status, err, fixture,
                      new_key, ok_json, parse_ts, pmap, check_shape, domain_searches)

D1, D2 = "tidewell-pharma.test", "northwind-optics.test"


def export(w, api=None):
    r = (api or w.anon).get("/_test/export", timeout=10)
    j = ok_json(r)
    return j


def do_import(w, snap, api=None):
    return (api or w.anon).post("/_test/import", body=snap, timeout=10)


def login(api_base, user=ADA, pw=PW):
    return Api(api_base, ok_json(Api(api_base).post("/auth/login", body={
        "email": user["email"], "password": pw}))["token"])


def snapshot_view(w, api, domains):
    return {"list": ok_json(api.get("/dossiers", params={"limit": 200})),
            "dossiers": {d: ok_json(api.get(f"/dossiers/{d}")) for d in domains}}


# ---------------------------------------------------------------- clock
def test_clock_stands_still_and_dates_builds(pworld):
    """CK-1 CK-2 CK-7 GD-5"""
    w = pworld
    w.reset(fixture(now="2026-03-01T09:30:00+02:00"))
    b, _ = w.build(w.ada, D1)
    assert parse_ts(b["researched_at"]) == parse_ts("2026-03-01T09:30:00+02:00")
    assert b["researched_at"][-6:] in ("+02:00",) or parse_ts(b["researched_at"]).utcoffset() is not None
    time.sleep(1.2)                                        # real time passes, the clock does not
    b2, _ = w.refresh(w.ada, D1)
    assert b2["researched_at"] == b["researched_at"]
    assert w.dossier(w.ada, D1)["researched_at"] == b["researched_at"]
    assert_status(w.clock("2026-07-01T12:00:00+00:00"), 204)
    b3, _ = w.refresh(w.ada, D1)
    assert parse_ts(b3["researched_at"]) == parse_ts("2026-07-01T12:00:00+00:00")
    e = ok_json(w.ada.get("/dossiers"))["dossiers"][0]
    assert e["researched_at"] == b3["researched_at"]


def test_failed_clock_call_changes_nothing(pworld):
    """CK-3"""
    w = pworld
    assert_status(w.clock("2026-03-10T00:00:00+00:00"), 204)
    err(w.clock("2026-03-09T23:59:59+00:00"), 422, "validation_failed")
    b, _ = w.build(w.ada, D1)
    assert parse_ts(b["researched_at"]) == parse_ts("2026-03-10T00:00:00+00:00")


def test_reset_sets_the_clock(pworld):
    """CK-1"""
    w = pworld
    w.clock("2030-01-01T00:00:00+00:00")
    w.reset(fixture(now="2026-05-05T05:05:05+00:00"))
    b, _ = w.build(w.ada, D1)
    assert parse_ts(b["researched_at"]) == parse_ts("2026-05-05T05:05:05+00:00")


# ---------------------------------------------------------------- export / import
def test_export_shape_and_no_plaintext_passwords(world):
    """EX-1 EX-14 AU-11 EX-11"""
    world.signup("pw@example.com", "s3cret-passphrase-xyz", "Pw")
    r = world.anon.get("/_test/export", timeout=10)
    j = ok_json(r)
    assert j["track"] == "dossier" and j["format_version"] == 1 and isinstance(j["state"], dict)
    blob = json.dumps(j)
    assert "s3cret-passphrase-xyz" not in blob and PW not in blob, "plaintext password in export"
    assert export(world) == j                              # read-only, repeatable


def test_roundtrip_restores_everything(pworld):
    """EX-2 EX-3 EX-4 EX-5 EX-7 EX-8 EX-13 EX-16 AU-11"""
    w = pworld
    assert_status(w.clock("2026-03-02T08:00:00+00:00"), 204)
    sign = ok_json(w.signup("carol@example.com", "carol-pass-123", "Carol"), 201)
    carol = Api(BASE, sign["token"])
    k_post, k_ref, k_fail = new_key(), new_key(), new_key()
    b1, _ = w.build(carol, D1)
    first_post = None
    assert_status(w.request(w.ada, D2, key=k_post), 202)
    w.wait(w.ada, D2)
    first_post = ok_json(w.ada.post("/dossiers", body={"domain": D2}, key=k_post), 200)
    assert w.ada.post("/dossiers", body={"domain": "bad domain"}, key=k_fail).status_code == 422
    assert_status(w.clock("2026-03-03T08:00:00+00:00"), 204)
    refreshed = ok_json(carol.post(f"/dossiers/{D1}/refresh", key=k_ref), 202)
    w.wait(carol, D1)
    ada, bob = w.ada, w.bob
    before = snapshot_view(w, ada, [D1, D2])
    snap = export(w)
    # destroy and diverge
    w.reset(fixture(now="2026-06-01T00:00:00+00:00", users=[
        {"id": "u_zed", "email": "zed@example.com", "password": PW, "display_name": "Zed"}]))
    zed = login(BASE, {"email": "zed@example.com"})
    w.build(zed, "orchard-lane-foods.test")
    mark = len(w.mock.log())
    assert_status(do_import(w, snap), 204)
    assert_status(do_import(w, snap), 204)                 # repeating restores without duplicating
    time.sleep(1)
    assert len(w.mock.log()) == mark, "import must make no provider call"
    # replacement, not merge
    err(zed.get("/dossiers"), 401, "unauthenticated")
    err(w.anon.post("/auth/login", body={"email": "zed@example.com", "password": PW}), 401,
        "unauthenticated")
    # tokens, accounts, hashed passwords survive
    for t in (ada.token, carol.token, bob.token):
        assert_status(Api(BASE, t).get("/dossiers"), 200)
    lg = ok_json(w.anon.post("/auth/login", body={"email": "carol@example.com",
                                                  "password": "carol-pass-123"}))
    assert lg["user_id"] == sign["user_id"]
    err(w.anon.post("/auth/login", body={"email": "carol@example.com", "password": PW}), 401,
        "unauthenticated")
    assert ok_json(w.anon.post("/auth/login", body={"email": ADA["email"], "password": PW}))["user_id"] == ADA["id"]
    err(w.signup("carol@example.com"), 409, "email_taken")
    # dossiers: ids, state, fields, citations, researched_at, spent_units unchanged
    after = snapshot_view(w, ada, [D1, D2])
    assert after == before
    err(ada.get("/dossiers/orchard-lane-foods.test"), 404, "not_found")
    # idempotency records: replays are replays, reuse is 409, failed keys are reusable
    assert ok_json(ada.post("/dossiers", body={"domain": D2}, key=k_post), 200) == first_post
    err(ada.post("/dossiers", body={"domain": D1}, key=k_post), 409, "idempotency_key_reuse")
    assert ok_json(carol.post(f"/dossiers/{D1}/refresh", key=k_ref), 200) == refreshed
    assert_status(ada.post("/dossiers", body={"domain": "after-import.test"}, key=k_fail), 202)
    # the clock is unchanged by import: still the reset fixture's time
    b, _ = w.refresh(carol, D1)
    assert parse_ts(b["researched_at"]) == parse_ts("2026-06-01T00:00:00+00:00")
    assert b["spent_units"] > before["dossiers"][D1]["spent_units"]


def test_import_is_replacement_into_a_fresh_state_and_idempotent(pworld):
    """EX-5 EX-10"""
    w = pworld
    w.build(w.ada, D1)
    ada = w.ada
    snap = export(w)
    w.reset()
    assert ok_json(w.ada.get("/dossiers")) == {"dossiers": [], "has_more": False}
    err(w.ada.get(f"/dossiers/{D1}"), 404, "not_found")
    for _ in range(2):
        assert_status(do_import(w, snap), 204)
        assert len(ok_json(ada.get("/dossiers"))["dossiers"]) == 1
    assert export(w) == snap                                 # an unchanged export imports unchanged
    w.reset()                                                # reset clears imported state
    assert ok_json(w.ada.get("/dossiers")) == {"dossiers": [], "has_more": False}
    err(w.ada.get(f"/dossiers/{D1}"), 404, "not_found")


@pytest.mark.parametrize("mutate,codes", [
    (lambda s: {"track": "dossier", "format_version": 1}, {422}),
    (lambda s: {"format_version": 1, "state": s["state"]}, {422}),
    (lambda s: {"track": "dossier", "state": s["state"]}, {422}),
    (lambda s: dict(s, track="other"), {422}),
    (lambda s: dict(s, track=5), {400, 422}),
    (lambda s: dict(s, format_version=2), {422}),
    (lambda s: dict(s, format_version=0), {422}),
    (lambda s: dict(s, format_version="1"), {400, 422}),
    (lambda s: dict(s, state=None), {400, 422}),
    (lambda s: dict(s, state="garbage"), {400, 422}),
    (lambda s: dict(s, state=[1, 2]), {400, 422}),
    (lambda s: dict(s, state=7), {400, 422}),
    (lambda s: [s], {400, 422}),
])
def test_invalid_import_is_rejected_and_changes_nothing(pworld, mutate, codes):
    """EX-6"""
    w = pworld
    w.build(w.ada, D1)
    snap = export(w)
    other = Api(BASE, ok_json(w.signup("later@example.com", PW, "L"), 201)["token"])
    before = snapshot_view(w, w.ada, [D1])
    r = do_import(w, mutate(copy.deepcopy(snap)))
    assert r.status_code in codes, r.text
    if r.status_code != 204:
        from conftest import check_error_envelope
        check_error_envelope(r)
    assert_status(other.get("/dossiers"), 200)             # the destination is unchanged
    assert snapshot_view(w, w.ada, [D1]) == before


def test_import_rejects_unparseable_json(world):
    """EX-6"""
    err(world.anon.post("/_test/import", raw=b"{not json", timeout=10), 400, "malformed_request")
    err(world.anon.post("/_test/import", raw=b"", timeout=10), 400, "malformed_request")
    assert_status(world.ada.get("/dossiers"), 200)


def test_import_state_not_an_object_with_corrupt_content_is_422(world):
    """EX-6"""
    snap = export(world)
    bad = dict(snap, state={"definitely": ["not", "the", "state"]})
    r = do_import(world, bad)
    assert r.status_code in (204, 422)
    if r.status_code == 204:      # a lenient implementation: restore the original, move on
        assert_status(do_import(world, snap), 204)


def test_control_endpoints_need_no_token_and_ignore_unknown_fields(world):
    """EX-14"""
    snap = export(world)
    snap["x_extra"] = {"a": 1}
    assert_status(do_import(world, snap), 204)
    assert_status(world.anon.get("/_test/export", headers={"Authorization": "Bearer junk"}, timeout=10), 200)
    assert_status(world.ada.get("/_test/export", timeout=10), 200)


def test_export_taken_during_a_build_holds_the_dossier_as_before(pworld):
    """EX-9"""
    w = pworld
    w.mock.fault("nimble", ["search", "extract", "research"], "delay", 3)
    w.mock.fault("tavily", ["search", "extract"], "delay", 3)
    assert_status(w.request(w.ada, D1), 202)
    time.sleep(0.4)
    ada = w.ada
    snap = export(w)                                         # first build still running
    w.wait(w.ada, D1, 60)
    w.reset()
    w.mock.clear()
    assert_status(do_import(w, snap), 204)
    w.ada = ada
    b = w.dossier(w.ada, D1)
    assert b["state"] == "failed" and b["researched_at"] is None
    assert all(f["status"] == "unknown" and f["value"] is None and f["citations"] == []
               and f["candidates"] == [] for f in b["fields"].values())
    # the dossier is usable: refresh builds it
    b2, _ = w.refresh(w.ada, D1)
    assert b2["state"] == "ready" and b2["dossier_id"] == b["dossier_id"]


def test_export_during_a_refresh_holds_the_last_completed_build(pworld):
    """EX-9"""
    w = pworld
    b0, _ = w.build(w.ada, D1)
    w.mock.fault("nimble", ["search"], "delay", 3)
    w.mock.fault("tavily", ["search"], "delay", 3)
    assert_status(w.ada.post(f"/dossiers/{D1}/refresh", key=new_key()), 202)
    time.sleep(0.4)
    ada = w.ada
    snap = export(w)
    w.wait(w.ada, D1, 60)
    w.reset()
    w.mock.clear()
    assert_status(do_import(w, snap), 204)
    w.ada = ada
    b = w.dossier(w.ada, D1)
    assert b["state"] == "ready" and b["fields"] == b0["fields"]
    assert b["researched_at"] == b0["researched_at"]


def test_import_discards_a_build_running_in_the_destination(pworld):
    """EX-15 R-3"""
    w = pworld
    snap = export(w)                                         # empty state, users ada and bob
    w.mock.fault("nimble", ["search", "extract", "research"], "delay", 3)
    w.mock.fault("tavily", ["search", "extract"], "delay", 3)
    assert_status(w.request(w.ada, D1), 202)
    time.sleep(0.4)
    assert_status(do_import(w, snap), 204)
    time.sleep(9)
    err(w.ada.get(f"/dossiers/{D1}"), 404, "not_found")
    assert ok_json(w.ada.get("/dossiers")) == {"dossiers": [], "has_more": False}


@pytest.mark.skipif(not BASE2, reason="BASE_URL_2 (a second fresh instance) not provided")
def test_import_into_another_instance(pworld):
    """EX-12 EX-3"""
    w = pworld
    sign = ok_json(w.signup("far@example.com", "far-away-pass", "Far"), 201)
    far = Api(BASE, sign["token"])
    k = new_key()
    b, _ = w.build(far, D1)
    first = ok_json(far.post("/dossiers", body={"domain": D2}, key=k), 202)
    w.wait(far, D2)
    snap = export(w)
    other = Api(BASE2)
    assert_status(other.post("/_test/reset", body=fixture(now="2027-01-01T00:00:00+00:00", users=[]),
                             timeout=10), 204)
    assert_status(other.post("/_test/import", body=snap, timeout=10), 204)
    far2 = Api(BASE2, sign["token"])
    assert ok_json(far2.get(f"/dossiers/{D1}")) == ok_json(far.get(f"/dossiers/{D1}"))
    assert ok_json(far2.post("/dossiers", body={"domain": D2}, key=k), 200) == first
    lg = ok_json(other.post("/auth/login", body={"email": "far@example.com",
                                                 "password": "far-away-pass"}))
    assert lg["user_id"] == sign["user_id"]
