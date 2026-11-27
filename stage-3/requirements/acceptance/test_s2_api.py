"""Stage 2 over the API: candidates, the selection rule, status, page kind and publication time,
browser text, web access/cost, rate limits, determinism. Needs the mock web (./corpus).
IDs (S2-*) in docstrings refer to ../LEDGER.md. Companies: gen_corpus.py (stage-2 section)."""
import json
import time
from types import SimpleNamespace

import httpx
import pytest

import s2model as m
from conftest import (BASE, MOCK, MOCK_TOKEN, FIELDS, Api, Mock, World, assert_status,
                      check_build, check_candidates, check_citations, check_shape, domain_searches,
                      new_key, ok_json, parse_ts, pmap, served_index, successful, CORPUS_S2)
from test_builds import check_cost_rules, cost_of

NEW = ["ashgrove-labs.test", "brightmoor-energy.test", "cobalt-harbor.test", "driftwood-games.test"]
A, B, C, D = NEW


@pytest.fixture(scope="module")
def s2():
    """The four stage-2 companies, each built once on a clean service (read-only afterwards)."""
    if not (BASE and MOCK):
        pytest.fail("BASE_URL and MOCK_URL are required")
    mock = Mock(MOCK, MOCK_TOKEN)
    w = World(mock)
    w.reset()
    out = SimpleNamespace(w=w, bodies={}, windows={})
    for d in NEW:
        out.bodies[d], out.windows[d] = w.build(w.ada, d)
    out.calls = mock.log()
    return out


def vals(fld):
    return [c["value"] for c in fld["candidates"]]


def urls(fld):
    return [c["url"] for c in fld["candidates"]]


# ------------------------------------------------------------------ candidates and the rule
@pytest.mark.parametrize("domain", NEW)
def test_candidates_are_exactly_what_the_evidence_supports(s2, domain):
    """S2-CA-1 S2-CA-2 S2-CA-3 S2-CA-4 S2-CA-5 S2-CA-6 S2-SEL-9 S2-CO-1 S2-PG-5 (every field: candidate
    set = every supported value once per evidence page; kind/published as the page header gives;
    retrieved_at = build time; selection and status by the rule; budget and spend)"""
    b = s2.bodies[domain]
    assert b["state"] == "ready"
    check_build(b, s2.calls)
    check_cost_rules(b, s2.windows[domain], domain)
    for name, fld in b["fields"].items():
        for c in fld["candidates"]:
            assert parse_ts(c["retrieved_at"]) == parse_ts("2026-03-01T09:00:00+00:00")


def test_authority_outranks_recency(s2):
    """S2-SEL-1 S2-SEL-8 S2-ST-2 (ashgrove legal_name: the older own page beats the newer aggregator)"""
    f = s2.bodies[A]["fields"]["legal_name"]
    assert vals(f) == ["Ashgrove Labs, Inc.", "Ashgrove Labs Holdings Ltd"]
    assert [c["kind"] for c in f["candidates"]] == ["own", "aggregator"]
    assert f["value"] == "Ashgrove Labs, Inc." and f["status"] == "contested"
    assert [c["selected"] for c in f["candidates"]] == [True, False]
    assert [c["url"] for c in f["citations"]] == ["https://ashgrove-labs.test/about"]


def test_recency_decides_within_an_authority(s2):
    """S2-SEL-2 S2-SEL-1 (ashgrove ceo: newer own page, older own page, then the newest of all but a news page)"""
    f = s2.bodies[A]["fields"]["ceo"]
    assert vals(f) == ["Sam Ortiz", "Dana Ruiz", "Pat Lee"]
    assert [c["kind"] for c in f["candidates"]] == ["own", "own", "news"]
    assert f["value"] == "Sam Ortiz" and f["status"] == "contested"


def test_a_candidate_without_publication_time_ranks_below_dated_ones(s2):
    """S2-SEL-3 S2-PG-4 (ashgrove headcount: a 2020 page beats a page with no Published line)"""
    f = s2.bodies[A]["fields"]["headcount_range"]
    assert vals(f) == ["201-500", "51-200"]
    assert f["candidates"][0]["published_at"] is not None and f["candidates"][1]["published_at"] is None
    assert urls(f) == ["https://ashgrove-labs.test/jobs", "https://ashgrove-labs.test/careers"]


def test_equal_instants_written_differently_tie_and_the_url_decides(s2):
    """S2-SEL-2 S2-SEL-4 S2-PG-3 (ashgrove founded_year: 00:00Z and 01:00+01:00 are one instant; /about < /registry)"""
    f = s2.bodies[A]["fields"]["founded_year"]
    assert vals(f) == [2011, 2010] and f["value"] == 2011 and f["status"] == "contested"
    assert urls(f) == ["https://ashgrove-labs.test/about", "https://ashgrove-labs.test/registry"]
    assert [c["kind"] for c in f["candidates"]] == ["own", "filing"]       # equal authority
    t = [m.parse_rfc3339(c["published_at"]) for c in f["candidates"]]
    assert t[0] == t[1]


def test_values_of_one_page_rank_by_code_point_and_by_number(s2):
    """S2-SEL-5 (same URL: Zagreb before Århus by code point; 9000000 before 10000000 as numbers)"""
    h = s2.bodies[A]["fields"]["hq_city"]
    assert vals(h) == ["Zagreb", "Århus"] and h["value"] == "Zagreb"
    f = s2.bodies[A]["fields"]["funding_total"]
    assert vals(f) == [9000000, 10000000] and f["value"] == 9000000 and f["status"] == "contested"
    assert len({c["url"] for c in f["candidates"]}) == 1


def test_urls_compare_by_code_point_and_a_page_is_one_candidate_per_value(s2):
    """S2-SEL-4 S2-CA-2 S2-CA-3 (driftwood: /About < /about < /about/; a value stated twice on a page is one candidate)"""
    f = s2.bodies[D]["fields"]
    ceo = f["ceo"]
    assert urls(ceo) == ["https://driftwood-games.test/About", "https://driftwood-games.test/about"]
    assert vals(ceo) == ["Zed Quinn", "Amy Yu"] and ceo["value"] == "Zed Quinn"
    fy = f["founded_year"]
    assert urls(fy) == ["https://driftwood-games.test/About", "https://driftwood-games.test/about",
                        "https://driftwood-games.test/about/"]
    assert vals(fy) == [2012, 2012, 2012]


def test_the_same_value_on_several_pages_is_known_and_cites_each(s2):
    """S2-ST-1 S2-CA-3 S2-SEL-7 S2-SEL-1 (driftwood: 2012 x3, $12M vs 12 million dollars, 120 people vs 90 employees)"""
    f = s2.bodies[D]["fields"]
    for name, n in (("founded_year", 3), ("funding_total", 2), ("headcount_range", 2)):
        fld = f[name]
        assert fld["status"] == "known" and len(fld["candidates"]) == n, (name, fld)
        assert [(c["url"], c["excerpt"], c["provider"]) for c in fld["citations"]] == \
            [(c["url"], c["excerpt"], c["provider"]) for c in fld["candidates"]]
    assert f["funding_total"]["value"] == 12000000
    assert [c["kind"] for c in f["funding_total"]["candidates"]] == ["news", "aggregator"]
    assert f["headcount_range"]["value"] == "51-200"


def test_a_field_without_candidates_is_unknown_with_empty_candidates(s2):
    """S2-ST-3 S2-CA-7 (driftwood has no legal name and no city anywhere)"""
    for name in ("legal_name", "hq_city"):
        assert s2.bodies[D]["fields"][name] == {"value": None, "status": "unknown",
                                                "citations": [], "candidates": []}


def test_contested_field_keeps_its_value_and_only_its_values_citations(s2):
    """S2-ST-2 S2-SEL-6 (every ashgrove field is contested: citations are the selected value's candidates in rank order)"""
    for name, fld in s2.bodies[A]["fields"].items():
        assert fld["status"] == "contested" and fld["value"] is not None
        sel = [c for c in fld["candidates"] if c["value"] == fld["value"]]
        assert [c["url"] for c in fld["citations"]] == [c["url"] for c in sel]
        assert fld["candidates"][0]["selected"] is True
        assert sum(c["selected"] for c in fld["candidates"]) == 1


def test_a_lower_authority_value_is_selected_only_without_a_higher_one(s2):
    """S2-SEL-1 S2-SEL-10 (cobalt: own and filing before news before aggregator whatever the dates)"""
    f = s2.bodies[C]["fields"]["ceo"]
    assert [c["kind"] for c in f["candidates"]] == ["own", "own", "own", "own", "news", "aggregator", "aggregator"]
    # brightmoor: a field whose only candidates are news / aggregator is selected from those
    g = s2.bodies[B]["fields"]["funding_total"]
    assert g["value"] == 5000000 and g["candidates"][0]["kind"] == "news"


def test_kind_and_publication_time_come_from_the_header_with_defaults(s2):
    """S2-PG-1 S2-PG-2 S2-PG-3 S2-PG-4 (cobalt: absent/unlisted Kind -> host rule; www. normalised; invalid Published -> null)"""
    want = {   # url: (kind, published instant | None, ceo)
        "https://newsy-corner.test/cobalt": ("own", "2026-03-01T00:00:00+00:00", "Gus Hill"),
        "https://www.cobalt-harbor.test/team": ("own", "2026-02-20T10:30:00.250000+00:00", "Ben Cole"),
        "https://cobalt-harbor.test/about": ("own", "2026-02-20T08:30:00+00:00", "Ada Marsh"),
        "https://cobalt-harbor.test/legacy": ("own", None, "Eve Ford"),
        "https://cobalt-harbor.test/press": ("news", "2026-03-02T00:00:00+00:00", "Hal Ivey"),
        "https://blog.cobalt-harbor.test/post": ("aggregator", None, "Cy Dunn"),
        "https://wirecast-daily.test/cobalt": ("aggregator", None, "Di Evans"),
    }
    f = s2.bodies[C]["fields"]["ceo"]
    assert urls(f) == list(want), "rank order: own by recency (undated last), news, aggregators by URL"
    for c in f["candidates"]:
        kind, pub, who = want[c["url"]]
        assert c["kind"] == kind and c["value"] == who, (c["url"], c["kind"], c["value"])
        if pub is None:
            assert c["published_at"] is None, (c["url"], c["published_at"])
        else:
            assert m.parse_rfc3339(c["published_at"]) == m.parse_rfc3339(pub), (c["url"], c["published_at"])
    assert f["value"] == "Gus Hill" and f["status"] == "contested"
    for fld in s2.bodies[C]["fields"].values():
        if fld is not f:
            assert fld == {"value": None, "status": "unknown", "citations": [], "candidates": []}


def test_candidates_are_the_last_ready_builds_and_retrieved_at_is_its_time(pworld):
    """S2-CA-5 S2-CA-6 S2-CA-8 S2-CA-9 (failed refresh keeps candidates; a running refresh shows the last ready build; a completed refresh replaces them)"""
    w = pworld
    d = "northwind-optics.test"
    b0, _ = w.build(w.ada, d)
    assert all(parse_ts(c["retrieved_at"]) == parse_ts("2026-03-01T09:00:00+00:00")
               for f in b0["fields"].values() for c in f["candidates"])
    assert "Mara Voss" in vals(b0["fields"]["ceo"])
    # a refresh that fails (every provider answers 500) leaves the last ready build's candidates
    w.mock.break_all()
    assert_status(w.clock("2026-03-04T10:00:00+00:00"), 204)
    bf, _ = w.refresh(w.ada, d)
    assert bf["state"] == "failed"
    assert bf["fields"] == b0["fields"] and bf["researched_at"] == b0["researched_at"]
    # a running refresh still shows them
    w.mock.clear()
    w.mock.epoch(1)
    w.mock.fault("nimble", ["search"], "delay", 1.5)
    w.mock.fault("tavily", ["search"], "delay", 1.5)
    assert_status(w.clock("2026-03-05T10:00:00+00:00"), 204)
    assert_status(w.ada.post(f"/dossiers/{d}/refresh", key=new_key()), 202)
    mid = w.dossier(w.ada, d)
    assert mid["state"] == "building" and mid["fields"] == b0["fields"]
    b1 = w.wait(w.ada, d, 40)
    assert b1["state"] == "ready"
    check_shape(b1)
    check_candidates(b1, epoch=1)
    assert "Mara Voss" not in vals(b1["fields"]["ceo"]) and vals(b1["fields"]["ceo"]) == ["Tomas Klein"]
    for f in b1["fields"].values():
        for c in f["candidates"]:
            assert parse_ts(c["retrieved_at"]) == parse_ts("2026-03-05T10:00:00+00:00") \
                == parse_ts(b1["researched_at"])


def test_the_listed_legal_name_is_the_selected_value(pworld):
    """S2-LS-1 (GET /dossiers lists the selected legal_name; a non-selected candidate does not match q)"""
    w = pworld
    for d in (A, B, D):
        w.build(w.ada, d)
    rows = {r["domain"]: r for r in ok_json(w.ada.get("/dossiers"))["dossiers"]}
    assert rows[A]["legal_name"] == "Ashgrove Labs, Inc." and rows[B]["legal_name"] == "Brightmoor Energy Ltd"
    assert rows[D]["legal_name"] is None
    hit = [r["domain"] for r in ok_json(w.ada.get("/dossiers", params={"q": "ashgrove labs, inc"}))["dossiers"]]
    assert hit == [A]
    miss = [r["domain"] for r in ok_json(w.ada.get("/dossiers", params={"q": "Holdings"}))["dossiers"]]
    assert A not in miss


def test_the_selected_value_is_a_function_of_the_candidates(pworld):
    """S2-DET-1 (ashgrove built, refreshed, and refreshed with tavily down: same candidates, same selection)"""
    w = pworld
    b0, _ = w.build(w.ada, A)
    b1, _ = w.refresh(w.ada, A)
    for name in FIELDS:
        assert [(c["url"], c["value"], c["kind"], c["published_at"]) for c in b0["fields"][name]["candidates"]] \
            == [(c["url"], c["value"], c["kind"], c["published_at"]) for c in b1["fields"][name]["candidates"]]
        assert (b0["fields"][name]["value"], b0["fields"][name]["status"]) == \
               (b1["fields"][name]["value"], b1["fields"][name]["status"])
    w.mock.break_all(("tavily",))
    b2, calls = w.refresh(w.ada, A)
    assert b2["state"] == "ready"
    check_build(b2, w.mock.log())
    for name in FIELDS:
        assert [(c["value"], c["url"]) for c in b2["fields"][name]["candidates"]] == \
            [(c["value"], c["url"]) for c in b0["fields"][name]["candidates"]]
        assert {c["provider"] for c in b2["fields"][name]["candidates"]} <= {"nimble"}


# ------------------------------------------------------------------ page text, web access, cost
def test_candidates_come_from_the_text_a_browser_shows(s2):
    """S2-TX-1 S2-TX-2 S2-TX-3 S2-WEB-1 (brightmoor: served text is stale or empty, the browser text is right)"""
    f = s2.bodies[B]["fields"]
    assert f["hq_city"]["value"] == "Bristol" and vals(f["hq_city"]) == ["Bristol"]
    assert f["founded_year"]["value"] == 2003 and vals(f["founded_year"]) == [2003]
    assert f["headcount_range"]["value"] == "51-200", "stated only on the rendered page"
    assert f["ceo"]["value"] == "Ravi Menon" and vals(f["ceo"]) == ["Ravi Menon"]
    assert f["legal_name"]["value"] == "Brightmoor Energy Ltd"
    stale = ("Leeds", "1999", "Tom Hale", "Press release archive")
    for fld in f.values():
        for c in fld["candidates"] + fld["citations"]:
            assert not any(s in c["excerpt"] for s in stale), c
    idx = served_index(s2.calls)
    for fld in f.values():
        for c in fld["candidates"]:
            assert any(p == c["provider"] and c["excerpt"] in t for p, t in idx[c["url"]]), \
                "S2-TX-3: the provider named served the text the excerpt was copied from"


def test_a_research_claim_that_is_not_supported_still_gets_its_page_read(s2):
    """S2-CA-4 S2-CA-10 (brightmoor funding: the claim ($7M, 'reportedly') is no candidate; its page's own $5M statement is)"""
    f = s2.bodies[B]["fields"]["funding_total"]
    assert vals(f) == [5000000] and f["status"] == "known"
    assert f["candidates"][0]["url"] == "https://wirecast-daily.test/brightmoor-press"
    assert f["candidates"][0]["kind"] == "news"
    assert any(c["method"] == "research" and c["status"] < 400 for c in s2.windows[B])
    # the research citation's page is not returned by any search: it was read by extract (or a browser)
    assert any(c["urls"] and "https://wirecast-daily.test/brightmoor-press" in c["urls"] or
               c["method"] == "load" and "https://wirecast-daily.test/brightmoor-press" in c["urls"]
               for c in s2.windows[B] if c["method"] in ("extract", "load")), \
        "the page a research claim cites is read like any other page"


def test_web_access_cost_matches_the_providers_ledger(s2):
    """S2-WEB-2 S2-CO-1 S2-CO-2 (spent_units = sum of logged costs; a rendering extract is 3 per URL; <= 80 per build)"""
    for d in NEW:
        calls = s2.windows[d]
        assert s2.bodies[d]["spent_units"] == cost_of(calls) <= 80
        for c in calls:
            if c["method"] == "extract" and c["provider"] == "nimble":
                assert c["cost"] in (len(c["urls"]), 3 * len(c["urls"]))
            if c["method"] == "session":
                assert c["cost"] == (2 if c["provider"] == "browserbase" else 0)
            if c["method"] == "load":
                assert c["cost"] in (0, 1)
            if c["status"] >= 400:
                assert c["cost"] == 0


def test_nimble_render_alone_is_enough_when_the_browser_vendors_fail(pworld):
    """S2-WEB-3 (kernel and browserbase answer every call with 500)"""
    w = pworld
    for p in ("kernel", "browserbase"):
        w.mock.fault(p, ["session", "browse"], "error")
    b, calls = w.build(w.ada, B)
    assert b["state"] == "ready"
    check_build(b, w.mock.log())
    assert b["fields"]["hq_city"]["value"] == "Bristol" and b["fields"]["ceo"]["value"] == "Ravi Menon"
    assert b["spent_units"] == cost_of(calls) <= 80


def test_concurrent_builds_stay_correct_and_within_budget(pworld):
    """S2-WEB-4 S2-CO-2 (six builds at once: browser sessions are capped at 4 per provider, every build ends ready and exact)"""
    w = pworld
    doms = NEW + ["northwind-optics.test", "tidewell-pharma.test"]
    for d in doms:
        assert_status(w.request(w.ada, d), 202)
    bodies = {d: w.wait(w.ada, d, 60) for d in doms}
    time.sleep(1)
    calls = w.mock.log()
    for d, b in bodies.items():
        assert b["state"] == "ready", (d, b["state"])
        check_build(b, calls)
        assert b["spent_units"] <= 80
    assert sum(b["spent_units"] for b in bodies.values()) == cost_of(calls)


# ------------------------------------------------------------------ rate limits
@pytest.mark.parametrize("mode", ["throttle", "rate_limit"])
def test_429_is_retried_costs_nothing_and_does_not_fail_the_build(pworld, mode):
    """S2-RL-1 S2-RL-2 S2-RL-3 S2-RL-4 (nimble answers 429 to the first attempt of each call / to three attempts in a row; tavily is down)"""
    w = pworld
    d = "ashgrove-labs.test"
    w.mock.break_all(("tavily",))
    w.mock.fault("nimble", ["search", "extract", "research"], mode)
    t0 = time.time()
    assert_status(w.request(w.ada, d), 202)
    b = w.wait(w.ada, d, 150)
    took = time.time() - t0
    time.sleep(1)
    calls = w.mock.log()
    refused = [c for c in calls if c["status"] == 429]
    assert refused, "the fault should have refused something"
    assert all(c["cost"] == 0 for c in refused)
    assert b["state"] == "ready", f"a 429 is a reason to wait and call again, not to give up ({took:.0f}s)"
    check_build(b, calls)
    assert b["spent_units"] == cost_of(calls) <= 80
    assert len(domain_searches(calls, d)) == 1
    if mode == "throttle":
        assert took <= 10 + 3 * len(refused) + 2, \
            f"time spent waiting after a 429 is not counted, other time is: {took:.1f}s with {len(refused)} refusals"


def test_reads_stay_fast_and_valid_while_a_build_waits_on_429s(pworld):
    """S2-RL-5 CV-10 (reads during a build that waits on 429s stay fast and valid)"""
    w = pworld
    d = "driftwood-games.test"
    w.mock.fault("nimble", ["search", "extract", "research"], "rate_limit")
    w.mock.fault("tavily", ["search", "extract"], "rate_limit")
    assert_status(w.request(w.ada, d), 202)
    t_end = time.time() + 6
    while time.time() < t_end:
        t0 = time.time()
        b = w.dossier(w.ada, d)
        assert time.time() - t0 < 2.0
        check_shape(b)
        ok_json(w.ada.get("/dossiers"))
        time.sleep(0.3)
    b = w.wait(w.ada, d, 150)
    assert b["state"] in ("ready", "failed")
    check_citations(b, w.mock.log())


# ------------------------------------------------------------------ one route for browser and API
@pytest.mark.parametrize("path", ["/", "/contested", "/signup", "/login",
                                  "/dossiers/ashgrove-labs.test", "/dossiers/ashgrove-labs.test/evidence"])
def test_browser_routes_answer_html_without_a_token(s2, path):
    """S2-UI-1 S2-UI-2 (Accept: text/html gets the UI, no bearer token needed to load a screen)"""
    r = httpx.get(BASE + path, headers={"Accept": "text/html,application/xhtml+xml"},
                  follow_redirects=True, timeout=5)
    assert r.status_code == 200, (path, r.status_code, r.text[:200])
    assert r.headers["content-type"].lower().startswith("text/html"), r.headers["content-type"]
    assert "<" in r.text and len(r.text) > 100


def test_the_dossier_route_serves_json_to_api_clients_and_html_to_browsers(pworld):
    """S2-UI-2 S2-UI-3 (same URL; JSON without Accept: text/html; an unknown dossier is 404 for both)"""
    w = pworld
    w.build(w.ada, A)
    url = f"{BASE}/dossiers/{A}"
    auth = {"Authorization": f"Bearer {w.ada.token}"}
    for accept in (None, "application/json", "*/*"):
        h = dict(auth, **({"Accept": accept} if accept else {}))
        r = httpx.get(url, headers=h, timeout=5)
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/json"), accept
        assert r.json()["domain"] == A and "candidates" in r.json()["fields"]["ceo"]
    r = httpx.get(url, headers=dict(auth, Accept="text/html"), follow_redirects=True, timeout=5)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    r = httpx.get(f"{BASE}/dossiers/nobody-here.test", headers=auth, timeout=5)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = httpx.get(f"{BASE}/dossiers/nobody-here.test", headers={"Accept": "text/html"},
                  follow_redirects=True, timeout=5)
    assert r.status_code in (200, 404) and r.headers["content-type"].startswith("text/html")
    r = httpx.get(url, timeout=5)      # no token, no Accept: still the API
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"


def test_the_browser_route_normalises_its_domain(pworld):
    """S2-UI-4 (WWW. and case in the path reach the same dossier; JSON carries the normalised domain)"""
    w = pworld
    w.build(w.ada, A)
    r = httpx.get(f"{BASE}/dossiers/WWW.Ashgrove-Labs.TEST.", headers={"Authorization": f"Bearer {w.ada.token}"},
                  timeout=5)
    assert r.status_code == 200 and r.json()["domain"] == A
