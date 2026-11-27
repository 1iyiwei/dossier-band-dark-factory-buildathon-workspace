"""Load and concurrency (§2 limits, §11). IDs in docstrings."""
import time

import pytest

from conftest import (Api, BASE, assert_status, check_citations, check_shape, new_key, ok_json,
                      pmap, domain_searches)
from test_builds import cost_of


def test_fifty_in_flight_mixed_requests_give_no_5xx_and_valid_bodies(pworld):
    """CC-1 CV-10 CV-11"""
    w = pworld
    domains = [f"load-{i:02d}.test" for i in range(10)] + ["tidewell-pharma.test",
                                                           "northwind-optics.test"]

    def op(i):
        d = domains[i % len(domains)]
        api = w.ada if i % 2 else w.bob
        k = i % 5
        if k == 0:
            return api.post("/dossiers", body={"domain": d}, key=new_key())
        if k == 1:
            return api.get(f"/dossiers/{d}")
        if k == 2:
            return api.get("/dossiers", params={"limit": 7, "offset": i % 4, "q": "load"})
        if k == 3:
            return api.post(f"/dossiers/{d}/refresh", key=new_key())
        return w.anon.get("/health")

    rs = pmap(op, range(150), workers=50)
    for r in rs:
        assert r.status_code in (200, 202, 404), (r.status_code, r.text[:200])
        if r.status_code >= 400:
            assert r.json()["error"]["code"] == "not_found"
    for d in domains:
        end = time.time() + 60
        while True:
            r = w.ada.get(f"/dossiers/{d}")
            if r.status_code == 404:
                break
            b = r.json()
            check_shape(b)
            if b["state"] != "building":
                break
            assert time.time() < end
            time.sleep(0.2)
    time.sleep(1)
    calls = w.mock.log()
    per = {}
    for c in calls:
        per.setdefault(c["query"] or "", []).append(c)
    # every dossier: spent_units equals the cost of the calls that were made for it
    total = sum(w.dossier(w.ada, d)["spent_units"] for d in domains
                if w.ada.get(f"/dossiers/{d}").status_code == 200)
    assert total == cost_of(calls), (total, cost_of(calls))


def test_many_concurrent_creations_each_build_once(pworld):
    """CC-1 CC-2 PD-6 CO-2"""
    w = pworld
    domains = [f"burst-{i}.test" for i in range(8)]
    rs = pmap(lambda i: w.request(w.ada if i % 2 else w.bob, domains[i % 8]), range(48))
    codes = sorted(r.status_code for r in rs)
    assert codes == [200] * 40 + [202] * 8, codes
    for d in domains:
        w.wait(w.ada, d, 60)
    time.sleep(1)
    calls = w.mock.log()
    for d in domains:
        assert len(domain_searches(calls, d)) == 1, d
    assert len(ok_json(w.ada.get("/dossiers", params={"limit": 200}))["dossiers"]) == 8


def test_reads_during_a_refresh_are_always_one_of_the_two_states(pworld):
    """CC-3 GD-4 CO-4"""
    w = pworld
    d = "northwind-optics.test"
    b0, _ = w.build(w.ada, d)
    w.mock.epoch(1)
    w.mock.fault("nimble", ["search"], "delay", 1)
    w.mock.fault("tavily", ["search"], "delay", 1)
    assert_status(w.ada.post(f"/dossiers/{d}/refresh", key=new_key()), 202)
    seen = []

    def read(_):
        r = w.bob.get(f"/dossiers/{d}")
        return r.json()

    for _ in range(12):
        for b in pmap(read, range(10)):
            check_shape(b)
            seen.append(b)
        if seen[-1]["state"] != "building":
            break
        time.sleep(0.1)
    old, final = b0["fields"], w.wait(w.ada, d, 40)["fields"]
    assert old != final
    for b in seen:
        if b["state"] == "building":
            assert b["fields"] == old, "fields of the last ready build while a build runs"
        else:
            assert b["fields"] == final or b["fields"] == old, "no half-written fields"
    # fields are never a mix: ceo and headcount move together with the build
    for b in seen:
        pair = (b["fields"]["ceo"]["value"], b["fields"]["headcount_range"]["value"])
        assert pair in {("Mara Voss", "51-200"), ("Tomas Klein", "201-500")}, pair
