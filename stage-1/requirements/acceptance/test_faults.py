"""Provider errors, slow providers, reset/import racing a build. Needs the mock web.
IDs in docstrings."""
import time

import pytest

from conftest import (BASE, Api, EXPECT, FIELDS, assert_status, check_build, check_citations,
                      check_expect, check_shape, domain_searches, err, new_key, ok_json, successful)
from test_builds import check_cost_rules, cost_of

D = "northwind-optics.test"


def unknown_all(b):
    return all(f == {"value": None, "status": "unknown", "citations": []} for f in b["fields"].values())


def test_all_providers_failing_ends_failed_and_free(pworld):
    """BD-2 CO-5 PV-3 PV-4"""
    w = pworld
    w.mock.break_all()
    b, calls = w.build(w.ada, D)
    assert b["state"] == "failed" and unknown_all(b) and b["researched_at"] is None
    assert b["spent_units"] == 0 == cost_of(calls)
    check_shape(b)
    by = {d["domain"]: d for d in ok_json(w.ada.get("/dossiers"))["dossiers"]}
    assert by[D]["state"] == "failed" and by[D]["legal_name"] is None
    rr = ok_json(w.ada.post("/dossiers", body={"domain": D}, key=new_key()), 200)
    assert rr["state"] == "failed"                                 # no automatic new build
    n = len(w.mock.log())
    time.sleep(0.5)
    assert len(w.mock.log()) == n


def test_failed_refresh_leaves_fields_and_researched_at(pworld):
    """BD-2 GD-4 GD-5 CO-5"""
    w = pworld
    b0, _ = w.build(w.ada, D)
    w.mock.break_all()
    assert_status(w.clock("2026-03-09T09:00:00+00:00"), 204)
    b1, calls = w.refresh(w.ada, D)
    assert b1["state"] == "failed"
    assert b1["fields"] == b0["fields"] and b1["researched_at"] == b0["researched_at"]
    assert b1["spent_units"] == b0["spent_units"] + cost_of(calls) == b0["spent_units"]
    w.mock.clear()
    b2, _ = w.refresh(w.ada, D)
    assert b2["state"] == "ready" and parse(b2["researched_at"]) > parse(b0["researched_at"])
    assert b2["spent_units"] > b0["spent_units"]


def parse(s):
    from conftest import parse_ts
    return parse_ts(s)


def test_nimble_alone_suffices_when_tavily_fails(pworld):
    """DEP-8"""
    w = pworld
    w.mock.break_all(("tavily",))
    b, calls = w.build(w.ada, "tidewell-pharma.test")
    assert b["state"] == "ready"
    check_build(b, w.mock.log())
    assert all(f["status"] == "known" for f in b["fields"].values())
    for f in b["fields"].values():
        assert {c["provider"] for c in f["citations"]} == {"nimble"}
    assert b["spent_units"] == cost_of(calls) <= 80


def test_research_failure_leaves_search_evidence(pworld):
    """BD-2 CO-5 PV-2 SU-8"""
    w = pworld
    w.mock.fault("nimble", ["research"], "error")
    b, calls = w.build(w.ada, "kestrel-freight.test")
    assert b["state"] == "ready"
    check_shape(b)
    check_citations(b, w.mock.log())
    assert b["fields"]["founded_year"]["value"] == 1998
    assert b["fields"]["legal_name"]["value"] == "Kestrel Freight GmbH"
    assert b["fields"]["ceo"]["status"] == "unknown"       # only a research claim carries it
    assert b["spent_units"] == cost_of(calls) <= 80
    assert len(domain_searches(calls, "kestrel-freight.test")) == 1


@pytest.mark.parametrize("mode", ["error", "rate_limit", "throttle"])
def test_search_errors_keep_the_invariants(pworld, mode):
    """CO-1 CO-2 CO-5 CO-10 PV-4 BD-2"""
    w = pworld
    w.mock.fault("nimble", ["search"], mode)
    b, calls = w.build(w.ada, "tidewell-pharma.test", timeout=60)
    time.sleep(1.5)
    calls = w.mock.log()
    assert b["state"] in ("ready", "failed")
    check_shape(b)
    check_citations(b, calls)
    assert cost_of(calls) <= 80 and b["spent_units"] == cost_of(calls)
    assert len(domain_searches(calls, "tidewell-pharma.test")) <= 1
    for c in calls:
        if c["status"] >= 400:
            assert c["cost"] == 0
    if b["state"] == "ready" and mode != "error":
        assert len(domain_searches(calls, "tidewell-pharma.test")) == 1
    if b["state"] == "failed":
        assert unknown_all(b)


def test_exactly_one_domain_query_search_even_after_a_refused_search(pworld):
    """CO-2 CO-10 (a search the provider refuses does not count; the build still makes exactly one)"""
    w = pworld
    w.mock.fault("nimble", ["search"], "throttle")
    b, _ = w.build(w.ada, "tidewell-pharma.test", timeout=60)
    time.sleep(1)
    calls = w.mock.log()
    if b["state"] == "ready":
        assert len(domain_searches(calls, "tidewell-pharma.test")) == 1
        refused = [c for c in calls if c["method"] == "search" and c["status"] >= 400]
        for c in refused:
            assert c["cost"] == 0


def test_slow_providers_are_waited_for_and_post_returns_at_once(pworld):
    """BD-5 BD-7 CO-4 CO-6"""
    w = pworld
    w.mock.fault("nimble", ["search", "extract", "research"], "delay", 3)
    w.mock.fault("tavily", ["search", "extract"], "delay", 3)
    t0 = time.time()
    assert_status(w.request(w.ada, "tidewell-pharma.test"), 202)
    assert time.time() - t0 < 1.5
    b = w.wait(w.ada, "tidewell-pharma.test", 120)
    time.sleep(5)
    calls = w.mock.log()
    check_shape(b)
    check_citations(b, calls)
    assert cost_of(calls) <= 80
    assert b["spent_units"] == cost_of(calls), "a call that timed out still costs its units"
    assert b["state"] == "ready" and all(f["status"] == "known" for f in b["fields"].values())


def test_reset_during_a_build_leaves_the_new_state_untouched(pworld):
    """R-3 BD-1"""
    w = pworld
    w.mock.fault("nimble", ["search", "research", "extract"], "delay", 3)
    w.mock.fault("tavily", ["search", "extract"], "delay", 3)
    assert_status(w.request(w.ada, "tidewell-pharma.test"), 202)
    time.sleep(0.5)
    w.anon.post("/_test/reset", body={"now": "2026-04-01T00:00:00+00:00", "users": [
        {"id": "u_cy", "email": "cy@example.com", "password": "correct horse",
         "display_name": "Cy"}]}, timeout=10)
    cy = Api(BASE, ok_json(w.anon.post("/auth/login", body={"email": "cy@example.com",
                                                             "password": "correct horse"}))["token"])
    time.sleep(9)                                  # the old build's calls finish meanwhile
    assert ok_json(cy.get("/dossiers")) == {"dossiers": [], "has_more": False}
    err(cy.get("/dossiers/tidewell-pharma.test"), 404, "not_found")
    # a new dossier for the same domain starts from scratch and builds normally
    w.mock.clear()
    assert_status(cy.post("/dossiers", body={"domain": "tidewell-pharma.test"}, key=new_key()), 202)
    b = w.wait(cy, "tidewell-pharma.test", 30)
    assert b["state"] == "ready" and b["researched_at"] == "2026-04-01T00:00:00+00:00"
    check_shape(b)


def test_build_results_survive_reset_reuse_of_domain(pworld):
    """R-1"""
    w = pworld
    b0, _ = w.build(w.ada, "tidewell-pharma.test")
    w.reset()
    err(w.ada.get("/dossiers/tidewell-pharma.test"), 404, "not_found")
    b1, calls = w.build(w.ada, "tidewell-pharma.test")
    assert b1["dossier_id"] and b1["spent_units"] == cost_of(calls)
