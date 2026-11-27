"""Stage 3: export/import keeps history, feed, builds (as_of, values) and tokens; and the service survives an abrupt
restart (Restarts). IDs (S3-*) in docstrings refer to ../LEDGER.md. Needs the meridian timeline (s3util.py)."""
import subprocess
import time

import pytest

from conftest import (ADA, BASE, BASE2, MOCK, PW, RESTART_CMD, Api, World, assert_status, err, fixture, new_key, ok_json,
                      parse_ts)
from s3util import (M, STEPS, T, as_of, changes_all, dt, full_view, history_of, run_timeline, values)


@pytest.fixture(scope="module")
def tl():
    if not (BASE and MOCK):
        pytest.fail("BASE_URL and MOCK_URL are required")
    return run_timeline()


def login(base, user=ADA):
    return Api(base, ok_json(Api(base).post("/auth/login", body={"email": user["email"],
                                                                 "password": user["password"]}))["token"])


def restart_service():
    """Kill the service abruptly, start it again, wait until it is healthy (RESTART_CMD, see README)."""
    subprocess.run(RESTART_CMD, shell=True, check=True, timeout=180)
    for _ in range(240):
        try:
            if Api(BASE).get("/health").status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError("the service is not healthy after the restart")


def export(api):
    j = ok_json(api.get("/_test/export", timeout=10))
    return j


# --------------------------------------------------------------------------- stage-3 export -> stage-3 import
def test_a_stage_3_export_survives_import_unchanged_on_another_instance(tl):
    """S3-UP-9 S3-UP-10 S3-UP-11 S3-AO-14 (history, feed with its seq, builds: as_of and values answer as in the exporting
    service; tokens, accounts and completed idempotent responses survive; the feed continues with larger seq)"""
    if not BASE2:
        pytest.skip("BASE_URL_2 (a second instance) is needed")
    src = tl.w.ada
    key = new_key()
    first = ok_json(src.post("/dossiers", body={"domain": "orchard-lane-foods.test"}, key=key), 202)
    tl.w.wait(src, "orchard-lane-foods.test", 20)
    zed = ok_json(Api(BASE).post("/auth/signup", body={"email": "zed@example.com", "password": "zed-password-1",
                                                      "display_name": "Zed"}), 201)
    before = {d: full_view(src, d) for d in (M,)}
    snap = export(src)
    dst_anon = Api(BASE2)
    assert_status(dst_anon.post("/_test/reset", body=fixture(now=T["0"]), timeout=10), 204)   # a known clock
    assert_status(dst_anon.post("/_test/import", body=snap, timeout=10), 204)
    dst = Api(BASE2, src.token)                               # the token held before the export
    after = {d: full_view(dst, d) for d in (M,)}
    assert after == before
    # restore is idempotent: import twice does not duplicate history or feed entries
    assert_status(dst_anon.post("/_test/import", body=snap, timeout=10), 204)
    assert full_view(dst, M) == before[M]
    # accounts, tokens and the completed idempotent response
    assert ok_json(dst_anon.post("/auth/login", body={"email": "zed@example.com", "password": "zed-password-1"}))[
        "user_id"] == zed["user_id"]
    assert_status(Api(BASE2, zed["token"]).get("/changes"), 200)
    r = dst.post("/dossiers", body={"domain": "orchard-lane-foods.test"}, key=key)
    assert ok_json(r, 200) == first
    # the feed continues after import: a new entry has a larger seq than every imported one
    feed0 = changes_all(dst)
    assert_status(dst_anon.post("/_test/clock", body={"now": "2026-08-01T09:00:00+00:00"}), 204)
    mock = tl.mock
    mock.epoch(0)
    assert_status(dst.post(f"/dossiers/{M}/refresh", key=new_key()), 202)
    tl.w.wait(dst, M, 30)
    feed1 = changes_all(dst)
    assert feed1[:len(feed0)] == feed0 and len(feed1) > len(feed0)
    assert all(e["seq"] > max(x["seq"] for x in feed0) for e in feed1[len(feed0):])
    # the imported builds are unchanged: as_of at the old times answers as before
    for k in T:
        assert (as_of(dst, M, T[k]).status_code, as_of(dst, M, T[k]).json()) == before[M][("asof", k)]
    h = history_of(dst, M)["fields"]["ceo"]
    assert [e["value"] for e in h[:5]] == [e["value"] for e in before[M]["hist"]["fields"]["ceo"]]
    assert h[-1]["learned_at"].startswith("2026-08-01") or dt(h[-1]["learned_at"]) == dt("2026-08-01T09:00:00+00:00")


def test_import_replaces_history_and_feed_on_the_same_instance(tl):
    """S3-UP-9 S3-UP-11 (an export taken, a later change made, the import restores: history, feed and as_of as exported)"""
    src = tl.w.ada
    snap = export(src)
    want = full_view(src, M)
    assert_status(tl.w.clock("2026-09-01T09:00:00+00:00"), 204)
    tl.mock.epoch(0)
    tl.w.refresh(src, M)
    assert len(changes_all(src)) > len(want["feed"])
    assert_status(Api(BASE).post("/_test/import", body=snap, timeout=10), 204)
    assert full_view(src, M) == want
    got = ok_json(as_of(src, M, "2026-09-02T00:00:00+00:00"))
    assert dt(got["researched_at"]) == dt(T["4"]), "the build made after the export is gone"


# --------------------------------------------------------------------------- restarts
@pytest.fixture(scope="module")
def tlr():
    """A fresh timeline, then: accounts, an idempotent request, an abrupt restart, and what the service answers."""
    if not RESTART_CMD:
        pytest.skip("RESTART_CMD is not set")
    tl = run_timeline()
    w = tl.w
    api = w.ada
    key = new_key()
    first = ok_json(api.post("/dossiers", body={"domain": "orchard-lane-foods.test"}, key=key), 202)
    w.wait(api, "orchard-lane-foods.test", 20)
    zed = ok_json(Api(BASE).post("/auth/signup", body={"email": "zed@example.com", "password": "zed-password-1",
                                                      "display_name": "Zed"}), 201)
    before = {"m": full_view(api, M), "o": full_view(api, "orchard-lane-foods.test", keys=[])}
    seq_before = max(e["seq"] for e in changes_all(api))
    restart_service()                                     # right after the last response: no time to settle
    api2 = Api(BASE, api.token)
    after = {"m": full_view(api2, M), "o": full_view(api2, "orchard-lane-foods.test", keys=[])}
    login_ = Api(BASE).post("/auth/login", body={"email": "zed@example.com", "password": "zed-password-1"})
    tok = Api(BASE, zed["token"]).get("/changes")
    rep = api2.post("/dossiers", body={"domain": "orchard-lane-foods.test"}, key=key)
    tl.mock.epoch(0)                                      # the web moves; no clock call: the clock stands where it was
    assert_status(api2.post(f"/dossiers/{M}/refresh", key=new_key()), 202)
    body = w.wait(api2, M, 40)
    return tl, {"before": before, "after": after, "seq_before": seq_before,
                "seq_after": max(e["seq"] for e in changes_all(api2)), "first": first, "login": login_.status_code,
                "token": tok.status_code, "replay": rep, "researched_at": body["researched_at"],
                "clock": T["4"]}


def test_an_abrupt_restart_loses_nothing_when_no_build_is_running(tlr):
    """S3-RS-1 S3-RS-2 S3-RS-3 S3-RS-4 S3-RS-5 S3-RS-6 (accounts and tokens; every dossier answering as before, with and
    without as_of, values, history, the list; the feed with the same seq; a replay of a completed idempotent request;
    the clock reads the time it read before the stop; entries added later have larger seq)"""
    tl, st = tlr
    assert st["before"]["m"] == st["after"]["m"], "dossier answers differ after the restart"
    assert st["before"]["o"] == st["after"]["o"]
    assert st["login"] == 200 and st["token"] == 200
    assert st["replay"].status_code == 200 and st["replay"].json() == st["first"]
    assert dt(st["researched_at"]) == dt(st["clock"]), "the clock reads the time it read before the stop"
    assert st["seq_after"] > st["seq_before"], "an entry added after the restart has a larger seq"


def test_a_second_restart_right_after_the_first_changes_nothing(tlr):
    """S3-RS-1 S3-RS-3 (still the same feed, history, as_of and dossiers)"""
    tl, _ = tlr
    api = Api(BASE, tl.w.ada.token)
    want = full_view(api, M)
    restart_service()
    assert full_view(Api(BASE, tl.w.ada.token), M) == want


def test_reset_clears_history_and_feed(tlr):
    """S3-UP-12 (reset clears everything: no dossier, no feed entry; a dossier built again starts a history afresh)"""
    assert_status(Api(BASE).post("/_test/reset", body=fixture(), timeout=10), 204)
    api = login(BASE)
    assert changes_all(api) == []
    err(api.get(f"/dossiers/{M}/history"), 404, "not_found")
    err(api.get(f"/dossiers/{M}", params={"as_of": T["4"]}), 404, "not_found")


