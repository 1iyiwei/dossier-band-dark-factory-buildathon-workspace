"""Stage 4 provider failure: a provider may answer any call with an error (5xx or 429) and the build continues.
IDs (S4-*) in docstrings refer to ../LEDGER.md. Needs the mock web."""
import time

import pytest

import s3model as s3
from conftest import (CORPUS_S2, UNKNOWN, assert_status, check_build, check_citations, check_shape, new_key, ok_json,
                      parse_ts)
from s3util import dt
from test_builds import cost_of
from test_s4_batches import FLEET, check_batch_shape, post_batch, wait_batch

LF, HR, BM = "lumen-forge.test", "hollow-reach.test", "brightmoor-energy.test"


def charge_free(calls):
    for c in calls:
        if c["status"] >= 400:
            assert c["cost"] == 0, f"S4-PF-4 a refused call costs nothing: {c}"


@pytest.mark.parametrize("mode", ["error", "rate_limit"])
@pytest.mark.parametrize("domain", [LF, HR])
def test_a_provider_that_always_fails_does_not_cost_the_evidence_nimble_gives(pworld, mode, domain):
    """S4-PF-1 S4-PF-4 S4-OR-5 (every call to tavily, kernel and browserbase fails, nimble answers: ready, every field known
    that nimble's evidence supports, with the origins, originals included; refused calls cost nothing)"""
    w = pworld
    w.mock.fault("tavily", ["search", "extract", "research"], mode)
    w.mock.fault("kernel", ["session"], mode)
    w.mock.fault("browserbase", ["session", "browse"], mode)
    b, calls = w.build(w.ada, domain, timeout=120)
    assert b["state"] == "ready"
    check_build(b, w.mock.log())
    charge_free(w.mock.log())
    assert b["spent_units"] == cost_of(calls) <= 80


def test_a_failing_research_run_leaves_what_search_and_extract_reach(pworld):
    """S4-PF-2 S4-PF-4 (brightmoor: its CEO is cited only by a research claim on a page no search returns: with every research
    run failing the build is ready, the fields are known exactly when search/extract evidence supports them)"""
    w = pworld
    for mode in ("error", "rate_limit"):
        w.reset()
        w.mock.fault("nimble", ["research"], mode)
        b, calls = w.build(w.ada, BM, timeout=120)
        assert b["state"] == "ready", mode
        check_shape(b)
        check_citations(b, w.mock.log())
        res, info, _ = s3.expected_all(BM, 0, CORPUS_S2, research=False)
        full, _, _ = s3.expected_all(BM, 0, CORPUS_S2, research=True)
        for name in ("legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total"):
            got = {(c["url"], c["value"]) for c in b["fields"][name]["candidates"]}
            must, may = res[name]["must"], res[name]["may"]
            if mode == "error":                  # no research run is ever answered
                assert must <= got <= must | may, (mode, name, got, must)
            else:        # a permanent 429 is answered on the fourth attempt (mock README): research may succeed
                assert must <= got <= full[name]["must"] | full[name]["may"] | may, (mode, name, got, must)
            assert (b["fields"][name]["status"] != "unknown") == bool(got), (mode, name)
        charge_free(w.mock.log())
        assert b["spent_units"] == cost_of(calls)


def test_when_every_call_to_every_provider_fails_the_build_fails_within_ten_seconds(pworld):
    """S4-PF-3 S4-PF-4 (first build: failed, every field unknown, researched_at null; a refresh: failed, the fields as they
    were; both within 10 seconds of the request; nothing billed)"""
    w = pworld
    d = "fleet-alpha.test"
    w.mock.break_all(("nimble", "tavily"))
    t0 = time.time()
    b, calls = w.build(w.ada, d, timeout=15)
    assert time.time() - t0 <= 10.5, f"failed after {time.time() - t0:.1f}s"
    assert b["state"] == "failed" and b["researched_at"] is None and b["spent_units"] == 0
    assert all(f == UNKNOWN for f in b["fields"].values())
    w.mock.clear()
    ok, _ = w.refresh(w.ada, d)
    assert ok["state"] == "ready"
    w.mock.break_all(("nimble", "tavily"))
    assert_status(w.clock("2026-03-09T09:00:00+00:00"), 204)
    t0 = time.time()
    bad, calls = w.refresh(w.ada, d, timeout=15)
    assert time.time() - t0 <= 10.5
    assert bad["state"] == "failed" and bad["fields"] == ok["fields"] and bad["researched_at"] == ok["researched_at"]
    assert bad["spent_units"] == ok["spent_units"] and cost_of(calls) == 0


def test_throttled_calls_are_made_again_and_the_build_still_completes(pworld):
    """S4-PF-1 S4-PF-4 (the first attempt of every distinct call is answered 429: the build repeats them; ready, the full
    evidence; the refused attempts cost nothing)"""
    w = pworld
    for p in ("nimble", "tavily"):
        w.mock.fault(p, ["search", "extract", "research"], "throttle")
    b, calls = w.build(w.ada, LF, timeout=150)
    assert b["state"] == "ready"
    check_build(b, w.mock.log())
    charge_free(w.mock.log())
    assert b["spent_units"] == cost_of(w.mock.log()) <= 80


def test_a_batch_whose_providers_all_fail_ends_done_with_failed_dossiers_and_no_spend(pworld):
    """S4-PF-3 S4-BA-7 S4-BA-8 (every call fails: each build ends failed, the batch is done, spent 0)"""
    w = pworld
    w.mock.break_all(("nimble", "tavily"))
    j = ok_json(post_batch(w.ada, FLEET[:3], 100), 202)
    done = wait_batch(w.ada, j["batch_id"], 60)
    check_batch_shape(done, FLEET[:3], 100)
    assert done["spent_units"] == 0 and [d["state"] for d in done["dossiers"]] == ["failed"] * 3
    assert cost_of(w.mock.log()) == 0


def test_a_batch_with_one_provider_down_still_researches_everything(pworld):
    """S4-PF-1 S4-BA-4 (tavily down: all three builds ready; spent = what nimble billed)"""
    w = pworld
    w.mock.break_all(("tavily",))
    mark = len(w.mock.log())
    j = ok_json(post_batch(w.ada, FLEET[:3], 200), 202)
    done = wait_batch(w.ada, j["batch_id"], 60)
    time.sleep(0.3)
    assert [d["state"] for d in done["dossiers"]] == ["ready"] * 3
    assert done["spent_units"] == cost_of(w.mock.log()[mark:])
    for d in FLEET[:3]:
        check_build(w.dossier(w.ada, d), w.mock.log())
