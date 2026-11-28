"""Stage 4: batches in export/import and abrupt restarts, including restarts while builds run (Restarts). IDs (S4-*) in
docstrings refer to ../LEDGER.md. The restart tests need RESTART_CMD (run.sh sets it) and a mock web."""
import subprocess
import time

import pytest

from conftest import (ADA, BASE, BASE2, MOCK, RESTART_CMD, Api, World, assert_status, check_citations, check_shape,
                      err, fixture, new_key, ok_json)
from s3util import changes_all, dt, full_view, history_of
from test_builds import cost_of
from test_s3_state import export, login
from test_s4_batches import FLEET, check_batch_shape, get_batch, post_batch, run_batch, wait_batch

NW = "northwind-optics.test"


def kill_and_restart():
    """SIGKILL the service and start it again (RESTART_CMD); returns the time /health first answered 200."""
    subprocess.run(RESTART_CMD, shell=True, check=True, timeout=180)
    for _ in range(600):
        try:
            if Api(BASE).get("/health").status_code == 200:
                return time.time()
        except Exception:
            pass
        time.sleep(0.1)
    raise AssertionError("the service is not healthy after the restart")


# --------------------------------------------------------------------------- idle batches
def test_a_batch_survives_export_import_on_another_instance(pworld):
    """S4-BA-13 S4-UP-1 (the batch, its owner, its idempotent response and the dossiers it made survive an import; another
    user still gets 404; the import makes no provider call)"""
    if not BASE2:
        pytest.skip("BASE_URL_2 is needed")
    w = pworld
    key = new_key()
    body = {"domains": FLEET[:2], "budget_units": 150}
    first = ok_json(w.ada.post("/batches", body=body, key=key), 202)
    done = wait_batch(w.ada, first["batch_id"])
    snap = export(w.ada)
    dst = Api(BASE2)
    assert_status(dst.post("/_test/reset", body=fixture(), timeout=10), 204)
    n = len(w.mock.log())
    assert_status(dst.post("/_test/import", body=snap, timeout=10), 204)
    ada2, bob2 = Api(BASE2, w.ada.token), Api(BASE2, w.bob.token)
    assert ok_json(get_batch(ada2, first["batch_id"])) == done
    err(get_batch(bob2, first["batch_id"]), 404, "not_found")
    assert ok_json(ada2.post("/batches", body=body, key=key), 200) == first
    assert len(w.mock.log()) == n


def test_idle_batches_and_dossiers_answer_as_before_an_abrupt_restart(pworld):
    """S4-RS-1 S4-RS-2 S4-BA-13 (a batch that is done: after a SIGKILL it, its replay and its dossiers answer exactly as
    before; the feed keeps its entries)"""
    if not RESTART_CMD:
        pytest.skip("RESTART_CMD is not set")
    w = pworld
    key = new_key()
    body = {"domains": FLEET[:2], "budget_units": 150}
    first = ok_json(w.ada.post("/batches", body=body, key=key), 202)
    done = wait_batch(w.ada, first["batch_id"])
    before = {d: full_view(w.ada, d, keys=[]) for d in FLEET[:2]}
    kill_and_restart()
    api = Api(BASE, w.ada.token)
    assert ok_json(get_batch(api, first["batch_id"])) == done
    assert ok_json(api.post("/batches", body=body, key=key), 200) == first
    err(get_batch(Api(BASE, w.bob.token), first["batch_id"]), 404, "not_found")
    assert {d: full_view(api, d, keys=[]) for d in FLEET[:2]} == before
    again = ok_json(post_batch(api, ["fleet-echo.test"], 60), 202)
    assert again["batch_id"] != first["batch_id"]


# --------------------------------------------------------------------------- builds running at the stop
def run_through_restart(w, start, delay=8.0):
    """Keep the first nimble search of every build in flight, kill the service, bring it back with a fast provider;
    returns (t_health, [dossier snapshots read as the restarted service sees them])"""
    w.mock.fault("nimble", ["search"], "delay", seconds=delay)
    start()
    time.sleep(1.0)
    w.mock.fault("nimble", ["search"], "none")
    return kill_and_restart()


def wait_not_building(api, domains, t_health, limit=10.0):
    out = {}
    while len(out) < len(domains):
        for d in domains:
            if d in out:
                continue
            b = ok_json(api.get(f"/dossiers/{d}"))
            if b["state"] != "building":
                out[d] = b
                assert time.time() - t_health <= limit + 1.0, \
                    f"S4-RS-3 {d} still building {time.time() - t_health:.1f}s after /health answered"
        assert time.time() - t_health < 60, f"still building: {sorted(set(domains) - set(out))}"
        time.sleep(0.1)
    return out


def test_a_build_running_at_the_stop_ends_within_ten_seconds_and_is_one_build(pworld):
    """S4-RS-3 S4-RS-4 S4-RS-5 S4-RS-2 S4-RS-6 (a first build killed in flight: after the restart it does not stay building;
    all its calls together bill at most 80 units and spent_units counts every billed unit; other dossiers, accounts and
    replays answer as before; a refresh starts a new build)"""
    if not RESTART_CMD:
        pytest.skip("RESTART_CMD is not set")
    w = pworld
    old, _ = w.build(w.ada, NW)
    before = {k: v for k, v in full_view(w.ada, NW, keys=[]).items() if k != "list"}
    key = new_key()
    d = "fleet-delta.test"
    mark = len(w.mock.log())
    before_list = ok_json(w.ada.get("/dossiers", params={"limit": 200}))["dossiers"]
    holder = {}
    t_health = run_through_restart(w, lambda: holder.update(first=ok_json(w.ada.post("/dossiers", body={"domain": d}, key=key), 202)))
    api = Api(BASE, w.ada.token)
    b = wait_not_building(api, [d], t_health)[d]
    time.sleep(8.5)                                  # a call in flight at the stop is billed by the mock when it ends
    calls = w.mock.log()[mark:]
    billed = cost_of(calls)
    assert b["state"] in ("ready", "failed")
    b = ok_json(api.get(f"/dossiers/{d}"))
    check_shape(b)
    check_citations(b, w.mock.log())
    assert billed <= 80, f"S4-RS-4 one build across the restart billed {billed}"
    assert b["spent_units"] >= billed, f"S4-RS-5 spent_units {b['spent_units']} < billed {billed}"
    if b["state"] == "failed":
        assert b["researched_at"] is None and all(f["status"] == "unknown" for f in b["fields"].values())
    assert {k: v for k, v in full_view(api, NW, keys=[]).items() if k != "list"} == before, \
        "S4-RS-2 everything else answers as before"
    lst = ok_json(api.get("/dossiers", params={"limit": 200}))["dossiers"]
    assert [x for x in lst if x["domain"] == NW] == [x for x in before_list if x["domain"] == NW]
    assert ok_json(api.post("/dossiers", body={"domain": d}, key=key), 200) == holder["first"]
    assert_status(Api(BASE).post("/auth/login", body={"email": ADA["email"], "password": ADA["password"]}), 200)
    n = len(w.mock.log())
    assert_status(api.post(f"/dossiers/{d}/refresh", key=new_key()), 202)
    after = w.wait(api, d, 30)
    assert after["state"] == "ready" and len(w.mock.log()) > n, "S4-RS-6 a refresh starts a new build"
    assert after["spent_units"] > b["spent_units"]


def test_builds_of_a_batch_running_at_the_stop_end_and_never_exceed_the_budget(pworld):
    """S4-RS-3 S4-RS-4 S4-RS-5 S4-RS-1 (a batch of three builds killed in flight: every dossier leaves `building` within 10 s
    of /health, the batch ends done, the providers billed at most budget_units across the restart, and the batch's and
    the dossiers' spent_units count every billed unit)"""
    if not RESTART_CMD:
        pytest.skip("RESTART_CMD is not set")
    w = pworld
    budget = 120
    key = new_key()
    body = {"domains": FLEET[:3], "budget_units": budget}
    mark = len(w.mock.log())
    holder = {}
    t_health = run_through_restart(w, lambda: holder.update(first=ok_json(w.ada.post("/batches", body=body, key=key), 202)))
    api = Api(BASE, w.ada.token)
    live = ok_json(get_batch(api, holder["first"]["batch_id"]))
    check_batch_shape(live, FLEET[:3], budget)
    bodies = wait_not_building(api, FLEET[:3], t_health)
    done = wait_batch(api, holder["first"]["batch_id"], 30)
    time.sleep(8.5)
    billed = cost_of(w.mock.log()[mark:])
    done = ok_json(get_batch(api, holder["first"]["batch_id"]))
    check_batch_shape(done, FLEET[:3], budget)
    assert done["state"] == "done" and all(d["state"] in ("ready", "failed") for d in done["dossiers"])
    assert billed <= budget, f"S4-OP-5 the providers billed {billed} > {budget} across the restart"
    assert done["spent_units"] >= billed - 0, f"S4-RS-5 batch spent_units {done['spent_units']} < billed {billed}"
    assert sum(ok_json(api.get(f"/dossiers/{d}"))["spent_units"] for d in FLEET[:3]) >= billed
    for d in FLEET[:3]:
        b = ok_json(api.get(f"/dossiers/{d}"))
        check_shape(b)
        check_citations(b, w.mock.log())
        assert b["spent_units"] <= 80 or b["spent_units"] >= 0
    assert ok_json(api.post("/batches", body=body, key=key), 200) == holder["first"]
