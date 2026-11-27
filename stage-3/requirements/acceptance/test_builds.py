"""Builds, evidence/support, cost and budget, providers. Needs the mock web (./corpus).
IDs in docstrings. Companies and their labelled expectations: gen_corpus.py."""
import time

import pytest

from conftest import (EXPECT, FIELDS, check_build, check_expect, check_shape, domain_searches,
                      err, new_key, ok_json, parse_ts, served_index, successful, assert_status,
                      check_citations)

COMPANIES = sorted(d for d in EXPECT if d != "no-trace.test") + ["no-trace.test"]


def cost_of(calls):
    return sum(c["cost"] for c in calls)


def check_cost_rules(b, calls, domain, *, strict_one_search=True):
    """CO-1 CO-2 CO-3 CO-4 CO-7 CO-8 over the calls of exactly one build of a fresh dossier."""
    assert cost_of(calls) <= 80, f"CO-1 build spent {cost_of(calls)} > 80"
    assert b["spent_units"] == cost_of(calls), \
        f"CO-4 spent_units {b['spent_units']} != cost of provider calls {cost_of(calls)}"
    ok_searches = [c for c in successful(calls) if c["method"] == "search"]
    dom = [c for c in ok_searches if c["query"] == domain]
    if strict_one_search:
        assert len(dom) == 1, f"CO-2 {len(dom)} successful searches for the domain"
    else:
        assert len(dom) <= 1, f"CO-2 {len(dom)} successful searches for the domain"
    for c in calls:
        if c["method"] == "research":
            assert c["provider"] == "nimble"
            assert c["fields"] == sorted(FIELDS), f"CO-7 research asked for {c['fields']}"
            assert domain in (c["query"] or ""), "CO-7 research query must name the domain"
        if c["method"] == "extract" and c["provider"] == "nimble" and c["status"] < 400:
            # stage 2: a plain extract is 1 per URL, one that renders is 3 per URL (S2-CO-1)
            assert c["cost"] in (len(c["urls"]), 3 * len(c["urls"])), \
                f"nimble extract cost {c['cost']} for {len(c['urls'])} urls"
        if c["method"] == "extract" and c["provider"] == "tavily" and c["status"] < 400:
            assert c["cost"] == 2 * len(c["urls"])
    return dom


@pytest.mark.parametrize("domain", COMPANIES)
def test_company_build_is_supported_and_within_budget(pworld, domain, ratio):
    """BD-3 BD-4 SU-1 SU-2 SU-3 SU-4 SU-6 SU-7 SU-9 SU-10 SU-11 SU-12 SU-15 CO-1 CO-2 CO-3 CO-4 CO-7 CO-8 CO-9 CO-11 CO-12 A2-1 A3-1 A4-L A4-H A4-C A4-F A4-N A4-M A5-1"""
    w = pworld
    t0 = time.time()
    b, calls = w.build(w.ada, domain)
    took = time.time() - t0
    assert b["state"] == "ready", b["state"]
    assert took <= 10.5, f"BD-4 build took {took:.1f}s with instant providers"
    assert b["domain"] == domain
    check_build(b, w.mock.log())
    check_cost_rules(b, calls, domain)
    assert b["researched_at"] == "2026-03-01T09:00:00+00:00" or \
        parse_ts(b["researched_at"]) == parse_ts("2026-03-01T09:00:00+00:00")
    ratio(domain, b)


def test_research_only_facts_come_from_a_research_claim(pworld):
    """SU-8 BD-3 (kestrel ceo/funding exist only on an unsearchable page cited by research)"""
    w = pworld
    b, calls = w.build(w.ada, "kestrel-freight.test")
    assert b["fields"]["ceo"]["value"] == "Ines Duarte" and b["fields"]["funding_total"]["value"] == 12000000
    assert any(c["method"] == "research" and c["status"] < 400 for c in calls)
    for f in ("ceo", "funding_total"):
        assert all(c["url"].endswith("/leadership") for c in b["fields"][f]["citations"])


def test_research_claims_that_the_excerpt_does_not_support_are_not_asserted(pworld):
    """SU-7 (kestrel: hedged headcount claim, Porto depot claim, Facts header values)"""
    w = pworld
    b, _ = w.build(w.ada, "kestrel-freight.test")
    for f in ("headcount_range", "hq_city"):
        assert b["fields"][f] == {"value": None, "status": "unknown", "citations": [],
                                  "candidates": []}, f


def test_header_facts_are_not_evidence(pworld):
    """SU-3 SU-12"""
    w = pworld
    b, _ = w.build(w.ada, "kestrel-freight.test")
    for fld in b["fields"].values():
        for c in fld["citations"]:
            assert "Facts" not in c["excerpt"] and "Kind:" not in c["excerpt"]
    assert b["fields"]["hq_city"]["value"] is None and b["fields"]["ceo"]["value"] != "Pedro Alves"


def test_unrelated_company_pages_are_not_cited(pworld):
    """SU-11 (no-trace.test: a look-alike company's pages are served by searches)"""
    w = pworld
    b, calls = w.build(w.ada, "no-trace.test")
    assert b["state"] == "ready"
    assert all(f["status"] == "unknown" for f in b["fields"].values()), b["fields"]
    assert b["researched_at"] is not None
    assert domain_searches(calls, "no-trace.test")


def test_hedged_negated_and_foreign_currency_statements(pworld):
    """SU-10 (quillstone-bio): hedges, negations, EUR, conflicting numbers"""
    w = pworld
    b, _ = w.build(w.ada, "quillstone-bio.test")
    f = b["fields"]
    assert f["hq_city"]["value"] == "Zürich" and f["ceo"]["value"] == "Wen Zhao"
    assert f["funding_total"]["value"] == 4000000
    for name in FIELDS:
        for c in f[name]["citations"]:
            assert "Geneva" not in c["excerpt"] and "Basel" not in c["excerpt"]
            assert "Rosa Alvarez" not in c["excerpt"] and "$40M" not in c["excerpt"]
            assert "€" not in c["excerpt"] and "$60" not in c["excerpt"]


def test_value_formats_and_normalisation(pworld):
    """SU-5 SU-13 SU-14 SU-15 (tidewell, orchard, bluefin): A.4/A.5 forms"""
    w = pworld
    b, _ = w.build(w.ada, "tidewell-pharma.test")
    f = b["fields"]
    assert f["legal_name"]["value"] == "Tidewell Pharma plc"
    assert f["hq_city"]["value"] == "San Sebastián"
    assert f["ceo"]["value"] == "Mary Anne Cole"
    assert f["founded_year"]["value"] == 1987 and f["headcount_range"]["value"] == "1001-5000"
    assert f["funding_total"]["value"] == 12500000
    b, _ = w.build(w.ada, "orchard-lane-foods.test")
    f = b["fields"]
    assert f["funding_total"]["value"] == 1234500 and f["headcount_range"]["value"] == "51-200"
    assert f["ceo"]["value"] == "Anika Sørensen" and f["legal_name"]["value"] == "Orchard Lane Foods Limited"


def test_contradicting_sources_hold_one_value_with_matching_citations(pworld):
    """SU-6 S2-ST-2 (bluefin: aggregator disagrees on year, headcount, funding: contested, own site wins)"""
    w = pworld
    b, _ = w.build(w.ada, "bluefin-marine.test")
    for name in ("founded_year", "headcount_range", "funding_total"):
        fld = b["fields"][name]
        assert fld["status"] in ("known", "contested") and len(fld["citations"]) >= 1
        urls = {c["url"] for c in fld["citations"]}
        # every citation supports the one value (verified by check_build); at least one exists
    check_build(b, w.mock.log())
    for name, own in (("founded_year", 2005), ("headcount_range", "11-50"), ("funding_total", 3000000)):
        assert b["fields"][name]["status"] == "contested" and b["fields"][name]["value"] == own, \
            "the company's own site outranks the aggregator whatever its date"


def test_sentence_boundaries(pworld):
    """A1-1 SU-4 (harbor: 'Inc.' mid-sentence; two sentences in a line; split lines)"""
    w = pworld
    b, _ = w.build(w.ada, "harbor-signal.test")
    f = b["fields"]
    assert f["founded_year"]["value"] == 2012       # 'Harbor Signal, Inc. was founded in 2012.'
    assert f["headcount_range"]["status"] == "unknown"  # 'It employs 60 people.' names no company
    assert f["hq_city"]["value"] == "Oslo"
    for fld in f.values():
        for c in fld["citations"]:
            assert "2012. It employs" not in c["excerpt"]


# ------------------------------------------------------------------ build lifecycle
def test_refresh_reresearches_replaces_fields_and_dates_by_request_time(pworld):
    """RF-1 RF-4 GD-4 GD-5 GD-6 BD-1 CK-7 CO-4"""
    w = pworld
    d = "northwind-optics.test"
    b0, calls0 = w.build(w.ada, d)
    assert b0["fields"]["ceo"]["value"] == "Mara Voss"
    assert b0["researched_at"] == "2026-03-01T09:00:00+00:00"
    spent0 = b0["spent_units"]
    w.mock.epoch(1)
    w.mock.fault("nimble", ["search"], "delay", 1.5)
    w.mock.fault("tavily", ["search"], "delay", 1.5)
    assert_status(w.clock("2026-03-05T10:00:00+00:00"), 204)
    mark = len(w.mock.log())
    r = ok_json(w.ada.post(f"/dossiers/{d}/refresh", key=new_key()), 202)
    assert (r["dossier_id"], r["domain"], r["state"]) == (b0["dossier_id"], d, "building")
    assert_status(w.clock("2026-03-06T10:00:00+00:00"), 204)        # clock moves mid-build
    mid = w.dossier(w.ada, d)
    assert mid["state"] == "building"
    assert mid["fields"] == b0["fields"] and mid["researched_at"] == b0["researched_at"], \
        "while a later build runs the fields are those of the last ready build"
    assert mid["spent_units"] >= spent0
    b1 = w.wait(w.ada, d, 40)
    time.sleep(2)
    calls1 = w.mock.log()[mark:]
    assert b1["state"] == "ready" and b1["dossier_id"] == b0["dossier_id"]
    assert parse_ts(b1["researched_at"]) == parse_ts("2026-03-05T10:00:00+00:00"), \
        "researched_at is the clock time of the request that started the build"
    check_shape(b1)
    check_expect(b1, epoch=1)
    check_citations(b1, w.mock.log())
    assert b1["fields"]["legal_name"]["status"] == "unknown", "evidence vanished -> unknown"
    assert b1["fields"]["ceo"]["value"] == "Tomas Klein"
    assert cost_of(calls1) <= 80 and calls1
    assert len(domain_searches(calls1, d)) == 1
    assert b1["spent_units"] == spent0 + cost_of(calls1) == cost_of(w.mock.log())
    assert len(domain_searches(calls0, d)) == 1


def test_refresh_with_nothing_changed_still_calls_providers_and_spends(pworld):
    """RF-4 CO-2 CO-4"""
    w = pworld
    d = "tidewell-pharma.test"
    b0, _ = w.build(w.ada, d)
    b1, calls = w.refresh(w.ada, d)
    assert calls and len(domain_searches(calls, d)) == 1
    assert b1["spent_units"] == b0["spent_units"] + cost_of(calls) == cost_of(w.mock.log())
    assert cost_of(calls) <= 80
    assert [b1["fields"][f]["value"] for f in FIELDS] == [b0["fields"][f]["value"] for f in FIELDS]
    assert b1["state"] == "ready"


def test_refresh_while_building_starts_no_second_build(pworld):
    """RF-2 BD-1"""
    w = pworld
    w.mock.fault("nimble", ["search"], "delay", 2)
    w.mock.fault("tavily", ["search"], "delay", 2)
    d = "tidewell-pharma.test"
    first = ok_json(w.request(w.ada, d), 202)
    r = ok_json(w.ada.post(f"/dossiers/{d}/refresh", key=new_key()), 202)
    assert r == first
    r2 = ok_json(w.bob.post(f"/dossiers/{d}/refresh", key=new_key()), 202)
    assert r2 == first
    w.wait(w.ada, d, 40)
    time.sleep(2.5)
    assert len(domain_searches(w.mock.log(), d)) == 1


def test_spent_units_never_decrease_and_reads_stay_valid_during_builds(pworld):
    """GD-6 CC-3"""
    w = pworld
    d = "northwind-optics.test"
    w.build(w.ada, d)
    w.mock.fault("nimble", ["search"], "delay", 1)
    w.mock.fault("tavily", ["search"], "delay", 1)
    assert_status(w.ada.post(f"/dossiers/{d}/refresh", key=new_key()), 202)
    last = 0
    t0 = time.time()
    while time.time() - t0 < 30:
        b = w.dossier(w.ada, d)
        check_shape(b)
        assert b["spent_units"] >= last
        last = b["spent_units"]
        if b["state"] != "building":
            break
        time.sleep(0.05)
    assert b["state"] == "ready"
