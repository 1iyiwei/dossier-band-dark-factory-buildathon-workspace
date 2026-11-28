"""Stage 4: lineage header lines, own pages and lookalikes, origins, `origin` of candidates, `origins` and
`corroborated` of fields. IDs (S4-*) in docstrings refer to ../LEDGER.md. Companies (gen_corpus.py stage-4 section):
lumen-forge.test (copies, syndication, a lookalike), hollow-reach.test (Canonical chains), kindred-mark.test and
keen-lantern.test (Registrant, Kind and own pages)."""
from types import SimpleNamespace

import pytest

import s2model as m
import s3model as s3
from conftest import (BASE, CORPUS_S2, MOCK, MOCK_TOKEN, UNKNOWN, Mock, World, check_build, ok_json, served_index)
from s3util import dt

LF, HR, KM, KL = "lumen-forge.test", "hollow-reach.test", "kindred-mark.test", "keen-lantern.test"
T0 = "2026-03-01T09:00:00+00:00"


@pytest.fixture(scope="module")
def s4():
    if not (BASE and MOCK):
        pytest.fail("BASE_URL and MOCK_URL are required")
    mock = Mock(MOCK, MOCK_TOKEN)
    w = World(mock)
    w.reset()
    out = SimpleNamespace(w=w, bodies={}, windows={})
    for d in (LF, HR, KM, KL):
        out.bodies[d], out.windows[d] = w.build(w.ada, d)
        assert out.bodies[d]["state"] == "ready", d
    out.calls = mock.log()
    return out


def cands(b, field="ceo"):
    return {c["url"]: c for c in b["fields"][field]["candidates"]}


# --------------------------------------------------------------------------- Own pages, Registrant, lookalikes
def test_kind_own_needs_the_company_as_registrant(s4):
    """S4-OWN-1 S4-OWN-2 S4-LH-2 (a page that states `Kind: own` and is registered to another domain is an aggregator in
    its candidates; a page without a Kind line is own only on the company's host and registrant)"""
    want = {   # url -> kind of the candidate
        KM: {"https://www.kindred-mark.test/about": "own", "https://registry-one.test/km": "filing",
             "https://sloppy-host.test/km": "news", "https://kindredmark-corp.test/about": "aggregator",
             "https://partner-site.test/km": "aggregator", "https://kindred-mark.test/team": "own"},
        KL: {"https://keen-lantern.test/about": "own", "https://keen-lantern.test/partner-copy": "aggregator",
             "https://syndicate-host.test/kl": "aggregator", "https://keen-lantern.test/listed": "own"},
        LF: {"https://lumen-forge.test/about": "own", "https://lumen-forge-hq.test/about": "aggregator",
             "https://registry-open.test/lumen-forge": "filing"}}
    for d, kinds in want.items():
        b = s4.bodies[d]
        check_build(b, s4.calls)
        allc = {c["url"]: c["kind"] for f in b["fields"].values() for c in f["candidates"]}
        for url, kind in kinds.items():
            if url in allc:
                assert allc[url] == kind, f"{d} {url}: kind {allc[url]!r} != {kind!r}"
    ceo = cands(s4.bodies[KM])
    assert ceo["https://www.kindred-mark.test/about"]["kind"] == "own"
    assert ceo["https://kindredmark-corp.test/about"]["kind"] == "aggregator"      # a lookalike
    assert s4.bodies[KM]["fields"]["ceo"]["value"] == "Max Dunn", "the newest own page outranks the aggregators"
    ceo = cands(s4.bodies[KL])
    assert ceo["https://keen-lantern.test/partner-copy"]["kind"] == "aggregator"
    assert ceo["https://syndicate-host.test/kl"]["kind"] == "aggregator"
    assert s4.bodies[KL]["fields"]["ceo"]["value"] == "Rex Stone"


def test_registrant_lines_are_normalised_and_an_invalid_one_falls_back_to_the_host(s4):
    """S4-LH-1 S4-LH-2 S4-OR-4 S4-OR-8 S4-OWN-3 (origin = the normalised registrant; `WWW.Registry-One.TEST.` is registry-one.test;
    a Registrant that is not a domain gives the host of the page's own URL; a lookalike has the company's domain)"""
    c = cands(s4.bodies[KM])
    assert {u: x["origin"] for u, x in c.items()} == {
        "https://www.kindred-mark.test/about": "kindred-mark.test",      # own page on a www host: normalised
        "https://registry-one.test/km": "registry-one.test",             # Registrant: WWW.Registry-One.TEST.
        "https://sloppy-host.test/km": "sloppy-host.test",               # Registrant: https://sloppy-host.test/km
        "https://kindredmark-corp.test/about": "kindred-mark.test",      # a lookalike (Kind: own, other registrant)
        "https://partner-site.test/km": "partner-site.test",             # states own, registered to itself
        "https://kindred-mark.test/team": "kindred-mark.test"}
    c = cands(s4.bodies[KL])
    assert {u: x["origin"] for u, x in c.items()} == {
        "https://keen-lantern.test/about": "keen-lantern.test",
        "https://keen-lantern.test/partner-copy": "other-owner.test",    # no Kind line: no lookalike, the registrant
        "https://syndicate-host.test/kl": "keen-lantern.test",           # registered to the company
        "https://keen-lantern.test/listed": "keen-lantern.test"}


# --------------------------------------------------------------------------- origins: the four rules
def test_origin_rules_one_to_four_with_copies_syndication_and_a_lookalike(s4):
    """S4-OR-1 S4-OR-2 S4-OR-3 S4-OR-4 S4-OR-8 (lumen-forge: a copy and a copy of a copy have the origin of the original; a
    syndicated page has its First-Published-By domain; a lookalike has the company's domain; else the registrant)"""
    b = s4.bodies[LF]
    check_build(b, s4.calls)
    c = {}
    for f in b["fields"].values():
        for x in f["candidates"]:
            c[x["url"]] = x["origin"]
    want = {"https://lumen-forge.test/about": "lumen-forge.test",
            "https://copycat-data.test/lumen-forge": "lumen-forge.test",       # Canonical -> the own page
            "https://scrapehub.test/lf": "lumen-forge.test",                    # Canonical -> a copy -> the own page
            "https://lumen-forge-hq.test/about": "lumen-forge.test",            # a lookalike
            "https://wirecast-daily.test/lumen-raise": "wirecast-daily.test",
            "https://localpress.test/lumen-raise": "wirecast-daily.test",       # First-Published-By
            "https://tickerpost.test/lumen": "tickerpost.test",
            "https://registry-open.test/lumen-forge": "registry-open.test"}
    assert {u: o for u, o in c.items() if u in want} == {u: o for u, o in want.items() if u in c}
    assert set(c) == set(want), "every page of the evidence gives a candidate somewhere"


def test_many_urls_with_one_origin_are_one_source(s4):
    """S4-OR-7 S4-FK-1 S4-FK-2 S4-FK-3 (origins are the distinct origins of the selected value's candidates, sorted;
    corroborated needs two of them: three URLs of one origin do not corroborate)"""
    f = s4.bodies[LF]["fields"]
    assert (f["ceo"]["value"], f["ceo"]["origins"], f["ceo"]["corroborated"]) == ("Rhea Marsh", ["lumen-forge.test"], False)
    assert len(f["ceo"]["candidates"]) == 3, "three URLs, one source"
    assert (f["hq_city"]["value"], f["hq_city"]["origins"], f["hq_city"]["corroborated"]) == ("Basel", ["lumen-forge.test"], False)
    assert f["founded_year"]["value"] == 2012
    assert f["founded_year"]["origins"] == ["lumen-forge.test", "wirecast-daily.test"] and f["founded_year"]["corroborated"] is True
    assert f["funding_total"]["value"] == 12000000
    assert f["funding_total"]["origins"] == ["tickerpost.test", "wirecast-daily.test"] and f["funding_total"]["corroborated"] is True
    assert f["legal_name"]["value"] == "Lumen Forge AG"
    assert f["legal_name"]["origins"] == ["lumen-forge.test", "registry-open.test"] and f["legal_name"]["corroborated"] is True
    for name in ("headcount_range", "executives", "investors"):
        assert f[name] == UNKNOWN, name
    assert sorted(f["ceo"]["origins"]) == f["ceo"]["origins"]


def test_corroborated_since_is_the_build_when_two_origins_first_stood(s4):
    """S4-FK-4 S4-FK-1 (a first build: the corroborated fields have `corroborated_since` = the build's time, the others null)"""
    f = s4.bodies[LF]["fields"]
    for name in ("founded_year", "funding_total", "legal_name"):
        assert dt(f[name]["corroborated_since"]) == dt(T0), name
    for name in ("ceo", "hq_city", "headcount_range", "executives", "investors"):
        assert f[name]["corroborated_since"] is None, name


# --------------------------------------------------------------------------- Canonical chains
HR_ORIGIN = {
    "https://chain-a.test/hr": "orig-registry.test",       # A -> B -> C -> D: three Canonical URLs followed, then D's registrant
    "https://deep-a.test/hr": "deep-e.test",               # A -> B -> C -> D would follow a fourth: the host of that URL
    "https://cycle-x.test/hr": "cycle-x.test",             # x -> y -> x -> y, a fourth would be x: the host of x
    "https://orphan.test/hr": "gone-original.test",        # no provider serves the original: the host of its URL
    "https://selfref.test/hr": "selfref.test",             # Canonical is the page's own URL: rule 2 does not apply
    "https://wwwcanon.test/hr": "mixed-case.test",         # https://WWW.Mixed-Case.TEST/hr: normalised host, unserved
    "https://fpb-first.test/hr": "source-one.test"}        # First-Published-By (normalised) before Canonical


def test_canonical_chains_follow_at_most_three_urls(s4):
    """S4-OR-1 S4-OR-2 S4-OR-6 S4-OR-6b S4-LH-1 S4-OR-8 (hollow-reach: exactly three followed; a fourth gives the host of the
    URL; a cycle; an unserved original; a self-canonical page; a Canonical host with www and capitals; rule 1 before rule 2)"""
    b = s4.bodies[HR]
    check_build(b, s4.calls)
    got = {u: c["origin"] for u, c in cands(b).items()}
    assert got == HR_ORIGIN, {u: (got.get(u), HR_ORIGIN[u]) for u in HR_ORIGIN if got.get(u) != HR_ORIGIN[u]}


def test_a_build_obtains_each_original_that_rule_two_needs(s4):
    """S4-OR-5 S4-OR-9 (hollow-reach: the pages at the Canonical URLs a build follows were served to it by a provider;
    the fourth URL of a chain is not needed; the build stays within 80 units)"""
    idx = served_index(s4.windows[HR])
    needed = ["https://chain-b.test/hr", "https://chain-c.test/hr", "https://chain-d.test/hr",
              "https://deep-b.test/hr", "https://deep-c.test/hr", "https://deep-d.test/hr", "https://cycle-y.test/hr"]
    missing = [u for u in needed if u not in idx]
    assert not missing, f"originals rule 2 needs were never obtained from a provider: {missing}"
    assert s4.bodies[HR]["spent_units"] <= 80
    assert sum(c["cost"] for c in s4.windows[HR]) == s4.bodies[HR]["spent_units"]
    # a page is read as it reads any other: an original that is not in the evidence gives no candidate
    urls = {c["url"] for f in s4.bodies[HR]["fields"].values() for c in f["candidates"]}
    assert "https://chain-d.test/hr" not in urls and "https://deep-b.test/hr" not in urls, \
        "an original fetched only for its origin is not evidence (stage-1 §4: evidence = search results and research claims)"
