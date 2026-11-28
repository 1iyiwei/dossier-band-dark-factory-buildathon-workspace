"""Stage 3: `GET /dossiers/{domain}?as_of=` and `GET /dossiers/{domain}/values?true_at=`.
IDs (S3-*) in docstrings refer to ../LEDGER.md. Companies: meridian-ledger.test (five epochs, one failed build),
tally-wharf.test (sources that republish and correct themselves), northwind-optics.test (same-time builds)."""
import copy

import pytest

import s2model as m
import s3model as s3
from conftest import (UNKNOWN, BASE, CORPUS_S2, MOCK, MOCK_TOKEN, Api, Mock, World, assert_status, check_build, err,
                      fixture, new_key, ok_json, parse_ts)
from s3util import M, EIGHT, T, STEPS, as_of, dt, run_timeline, spent_until, values

TW = "tally-wharf.test"
TW_STEPS = [("0", 0, False), ("1", 1, False), ("2", 2, False)]


@pytest.fixture(scope="module")
def tl():
    if not (BASE and MOCK):
        pytest.fail("BASE_URL and MOCK_URL are required")
    return run_timeline()


@pytest.fixture(scope="module")
def tw():
    if not (BASE and MOCK):
        pytest.fail("BASE_URL and MOCK_URL are required")
    return run_timeline(TW, TW_STEPS)


def expected_as_of(tl, when):
    """The dossier as the service had it at `when`: the last ready build at or before it, else None."""
    last = None
    for s in tl.ready:
        if s.time <= when:
            last = s
    if last is None:
        return None
    b = copy.deepcopy(last.body)
    b["state"] = "ready"
    b["spent_units"] = spent_until(tl, when)
    return b


def same_dossier(got, want):
    assert got["dossier_id"] == want["dossier_id"] and got["domain"] == want["domain"]
    assert got["state"] == "ready"
    assert dt(got["researched_at"]) == dt(want["researched_at"])
    assert got["spent_units"] == want["spent_units"], (got["spent_units"], want["spent_units"])
    assert got["fields"] == want["fields"]


# --------------------------------------------------------------------------- as_of
@pytest.mark.parametrize("key", ["0", "1", "f", "2", "3", "4"])
def test_as_of_a_build_time_returns_that_build_as_it_was(tl, key):
    """S3-AO-1 S3-AO-2 S3-AO-3 S3-AO-4 S3-TF-9 (fields, candidates, researched_at of the latest ready build at or before
    as_of; state ready; spent_units the total of the builds up to as_of; later history and the failed build
    leave the earlier answer unchanged)"""
    when = dt(T[key])
    same_dossier(ok_json(as_of(tl.w.ada, M, T[key])), expected_as_of(tl, when))


def test_as_of_between_builds_and_after_the_last(tl):
    """S3-AO-1 S3-AO-5 (a time between builds answers with the earlier build; after the last build with the last; it is
    decided by learned_at, never by true_from; a failed build in between changes only the spend)"""
    for ts in ("2026-03-01T09:00:01+00:00", "2026-03-31T23:59:59+00:00"):
        same_dossier(ok_json(as_of(tl.w.ada, M, ts)), expected_as_of(tl, dt(ts)))
    ts = "2026-04-30T23:00:00+00:00"                                   # after the failed build, before build 2
    got = ok_json(as_of(tl.w.ada, M, ts))
    assert dt(got["researched_at"]) == dt(T["1"]) and got["fields"] == tl.ready[1].body["fields"]
    ts = "2035-01-01T00:00:00+00:00"
    last = ok_json(as_of(tl.w.ada, M, ts))
    now = tl.w.dossier(tl.w.ada, M)
    assert last == now and dt(last["researched_at"]) == dt(T["4"])
    # the true_from of build 2's leadership page (2026-01-01) is before build 0: it is still not part of as_of(build 0)
    assert ok_json(as_of(tl.w.ada, M, T["0"]))["fields"]["ceo"]["value"] == "Dana Ruiz"


def test_as_of_describes_the_selected_value_at_that_snapshot(tl):
    """S3-TF-9 (each field's true_from and learned_at in an as_of response are those of the selected value then:
    no later history is used)"""
    got = ok_json(as_of(tl.w.ada, M, T["2"]))["fields"]
    assert got["ceo"]["value"] == "Sam Ortiz" and got["ceo"]["true_from"] == "2026-01-01"
    assert dt(got["ceo"]["learned_at"]) == dt(T["2"])
    assert got["headcount_range"]["true_from"] == "2019-06-01" and dt(got["headcount_range"]["learned_at"]) == dt(T["0"])
    assert got["founded_year"]["value"] == 2003 and dt(got["founded_year"]["learned_at"]) == dt(T["2"])
    early = ok_json(as_of(tl.w.ada, M, T["0"]))["fields"]
    assert early["founded_year"] == UNKNOWN          # stage 4: with origins [], corroborated false, corroborated_since null
    assert early["headcount_range"]["true_from"] == "2020-01-01"
    assert early["ceo"]["learned_at"] is not None and dt(early["ceo"]["learned_at"]) == dt(T["0"])
    assert early["executives"]["value"] == [{"title": "cfo", "name": "Ana Silva"},
                                            {"title": "cto", "name": "Ben Okafor"}]


@pytest.mark.parametrize("ts,key", [("2026-04-01T11:00:00+02:00", "1"), ("2026-04-01T04:00:00-05:00", "1"),
                                    ("2026-04-01T09:00:00Z", "1"), ("2026-04-01T09:00:00.000000+00:00", "1"),
                                    ("2026-04-01T10:59:59.999+02:00", "0"), ("2026-04-01T08:59:59.999999+00:00", "0")])
def test_as_of_compares_instants_not_spellings(tl, ts, key):
    """S3-AO-6 (equivalent RFC 3339 timestamps with other offsets, a Z and fractions name the same instant)"""
    got = ok_json(as_of(tl.w.ada, M, ts))
    assert dt(got["researched_at"]) == dt(T[key])


@pytest.mark.parametrize("ts", ["2026-04-01T09:00:00", "2026-04-01", "yesterday", "1775034000", "", "2026-04-01T25:00:00+00:00",
                                "2026-13-01T00:00:00+00:00", "2026-04-31T00:00:00+00:00", "2026-04-01T09:00:00 +00:00",
                                "2026-04-01T09:00Z", "null"])
def test_as_of_that_is_not_an_rfc3339_timestamp_with_an_offset_is_422(tl, ts):
    """S3-AO-7"""
    err(as_of(tl.w.ada, M, ts), 422, "validation_failed")


def test_as_of_before_the_first_ready_build_and_unknown_dossiers_are_404(tl):
    """S3-AO-8 S3-AO-9 S3-AO-10 (no build completed ready at or before as_of; no dossier for the domain)"""
    err(as_of(tl.w.ada, M, "2026-03-01T08:59:59+00:00"), 404, "not_found")
    err(as_of(tl.w.ada, M, "1999-01-01T00:00:00+00:00"), 404, "not_found")
    err(as_of(tl.w.ada, "nobody-here.test", T["0"]), 404, "not_found")
    assert_status(as_of(tl.w.ada, M, T["0"]), 200)
    # without as_of the response is unchanged: the current dossier, with the seven fields
    now = tl.w.dossier(tl.w.ada, M)
    assert list(now["fields"]) == list(EIGHT) and now["state"] == "ready"
    assert dt(now["researched_at"]) == dt(T["4"])
    err(Api(BASE).get(f"/dossiers/{M}"), 401, "unauthenticated")


def test_as_of_path_domain_is_normalised(tl):
    """S3-AO-11 (as in §4)"""
    got = ok_json(as_of(tl.w.ada, "WWW.Meridian-Ledger.TEST.", T["1"]))
    assert got["domain"] == M and dt(got["researched_at"]) == dt(T["1"])


# --------------------------------------------------------------------------- values
TRUE_ATS = ["1999-01-01", "2020-12-31", "2021-03-31", "2021-04-01", "2022-01-01", "2025-08-31", "2025-09-01",
            "2025-09-30", "2025-10-01", "2025-11-01", "2025-12-01", "2025-12-31", "2026-01-01", "2026-03-19",
            "2026-03-20", "2026-03-25", "2026-04-01", "2026-04-30", "2026-05-01", "2026-06-15", "2030-01-01"]


def check_values(api, domain, builds, as_of_ts, true_at, tl_dossier=None):
    r = values(api, domain, true_at, as_of_ts)
    j = ok_json(r)
    assert set(j) >= {"domain", "true_at", "as_of", "fields"}, sorted(j)
    assert j["domain"] == domain and j["true_at"] == true_at
    assert dt(j["as_of"]) == dt(as_of_ts), j["as_of"]
    assert list(j["fields"]) == list(EIGHT)
    want = s3.values_at(builds, dt(as_of_ts), true_at)
    for name in EIGHT:
        f = j["fields"][name]
        assert set(f) >= {"value", "true_from", "citations"}, (name, sorted(f))
        w = want[name]
        ctx = (domain, as_of_ts, true_at, name)
        assert f["value"] == w["value"], (ctx, f["value"], w["value"])
        assert f["true_from"] == w["true_from"], (ctx, f["true_from"], w["true_from"])
        assert [c["url"] for c in f["citations"]] == w["urls"], (ctx, f["citations"], w["urls"])
        for c in f["citations"]:
            assert set(c) >= {"url", "excerpt", "provider"} and c["provider"] in m.PROVIDERS
        if w["value"] is None:
            assert f["true_from"] is None and f["citations"] == []
    return j


@pytest.mark.parametrize("key", ["0", "1", "f", "2", "3", "4"])
def test_values_follow_the_page_versions_known_at_as_of(tl, key):
    """S3-VA-1 S3-VA-2 S3-VA-3 S3-VA-4 S3-VA-5 S3-VA-6 S3-EX-12 (for every true_at: the candidates of the versions
    that hold on that date, chosen by the selection rule; value, true_from, citations; executives by title)"""
    for ta in TRUE_ATS:
        check_values(tl.w.ada, M, tl.builds, T[key], ta)


def test_values_literal_cases_from_the_version_rules(tl):
    """S3-VA-2 S3-VA-3 S3-VA-4 S3-VA-6 S3-VA-7 (hand-derived from the rules: a later version replaces earlier ones whose
    true_from is on or after its own; it ends the latest one it does not replace; null true_from holds from no date;
    a gathered page with no candidates ends the earlier version; a page that is no longer served never ends)"""
    api = tl.w.ada
    ceo = lambda as_of_key, ta: ok_json(values(api, M, ta, T[as_of_key]))["fields"]["ceo"]
    assert ceo("0", "2021-03-31")["value"] is None                      # nothing holds before 2021-04-01
    c = ceo("0", "2021-04-01")
    assert (c["value"], c["true_from"]) == ("Dana Ruiz", "2021-04-01") and len(c["citations"]) == 1
    assert ceo("1", "2026-03-19")["value"] == "Dana Ruiz"               # build 0's version stops on 2026-03-20
    assert (ceo("1", "2026-03-20")["value"], ceo("1", "2026-03-20")["true_from"]) == ("Lee Park", "2026-03-20")
    assert ceo("2", "2026-03-25")["value"] == "Sam Ortiz"               # build 2 replaces build 1 (2026-03-20 >= 2026-01-01)
    assert ceo("2", "2026-03-25")["true_from"] == "2026-01-01"
    assert ceo("2", "2025-12-31")["value"] == "Dana Ruiz"               # build 0's version now stops on 2026-01-01
    assert ceo("3", "2026-04-30")["value"] == "Sam Ortiz"
    # build 3 gathered the leadership page with no candidate: from 2026-05-01 only the aggregator (never ended) holds
    a = ceo("3", "2026-06-15")
    assert (a["value"], a["true_from"]) == ("Pat Lee", "2022-01-01")
    # build 4's leadership page has a null true_from: it replaces every earlier version of its URL and holds from no date
    for ta in ("2022-01-01", "2026-01-01", "2026-06-15"):
        a = ceo("4", ta)
        assert (a["value"], a["true_from"]) == ("Pat Lee", "2022-01-01"), ta
    assert ceo("4", "2021-12-31")["value"] is None and ceo("4", "2021-04-01")["value"] is None
    ex = lambda k, ta: ok_json(values(api, M, ta, T[k]))["fields"]["executives"]
    e = ex("4", "2025-09-01")
    assert e["value"] == [{"title": "cfo", "name": "Ana Silva"}, {"title": "cto", "name": "Fay Quinn"}]
    assert e["true_from"] == "2025-09-01"
    e = ex("4", "2025-08-31")                        # only the aggregator's cfo holds (never ended: not served again)
    assert e["value"] == [{"title": "cfo", "name": "Gus Hall"}] and e["true_from"] == "2022-01-01"
    assert ex("2", "2025-11-01")["value"] == [{"title": "cfo", "name": "Ana Silva"}, {"title": "cto", "name": "Ben Okafor"}]
    assert [x["name"] for x in ex("2", "2025-12-01")["value"]] == ["Ana Silva", "Dee Hart", "Cho Min"]
    assert ex("3", "2025-09-30")["value"][-1] == {"title": "cto", "name": "Ben Okafor"}
    assert ex("3", "2025-10-01")["value"][-1] == {"title": "cto", "name": "Eli Novak"}
    # citations of an executives member list every candidate with that title and name, members in order
    e = ex("2", "2025-12-01")
    assert [c["url"] for c in e["citations"]][0].endswith("/exec") and len(e["citations"]) == 3
    # headcount: one page, the same value: the later version replaces the earlier (true_from 2019-06-01 < 2020-01-01)
    h = ok_json(values(api, M, "2019-12-31", T["2"]))["fields"]["headcount_range"]
    assert (h["value"], h["true_from"]) == ("51-200", "2019-06-01")
    assert ok_json(values(api, M, "2019-05-31", T["2"]))["fields"]["headcount_range"]["value"] is None
    assert ok_json(values(api, M, "2019-12-31", T["1"]))["fields"]["headcount_range"]["value"] is None


def test_values_default_as_of_is_the_clock_and_is_echoed(tl):
    """S3-VA-8 (as_of defaults to the current time (§8): the same answer as at the last build, as_of echoed)"""
    d = ok_json(values(tl.w.ada, M, "2026-06-15"))
    assert dt(d["as_of"]) == dt(T["4"]), d["as_of"]
    e = ok_json(values(tl.w.ada, M, "2026-06-15", T["4"]))
    assert d["fields"] == e["fields"] and d["true_at"] == "2026-06-15"
    for name in EIGHT:
        assert set(d["fields"][name]) >= {"value", "true_from", "citations"}


def test_values_validation_and_not_found(tl):
    """S3-VA-9 S3-VA-10 (true_at missing or not YYYY-MM-DD, as_of not RFC 3339 with offset: 422; unknown dossier, or no
    ready build at or before as_of: 404; leap day accepted)"""
    api = tl.w.ada
    err(api.get(f"/dossiers/{M}/values"), 422, "validation_failed")
    for bad in ("", "2025-6-1", "20250601", "2025-02-30", "2023-02-29", "2025-13-01", "2025-06-01T00:00:00Z",
                "June 1", "2025/06/01", " 2025-06-01", "2025-06-1"):
        err(values(api, M, bad), 422, "validation_failed")
    for bad in ("2026-04-01T09:00:00", "2026-04-01", "nope", ""):
        err(values(api, M, "2025-06-01", bad), 422, "validation_failed")
    err(values(api, "nobody-here.test", "2025-06-01"), 404, "not_found")
    err(values(api, M, "2025-06-01", "2026-03-01T08:59:59+00:00"), 404, "not_found")
    assert_status(values(api, M, "2024-02-29"), 200)
    assert_status(values(api, "WWW.Meridian-Ledger.TEST.", "2024-02-29"), 200)
    err(Api(BASE).get(f"/dossiers/{M}/values", params={"true_at": "2025-06-01"}), 401, "unauthenticated")


# --------------------------------------------------------------------------- sources that correct themselves
@pytest.mark.parametrize("key", ["0", "1", "2"])
def test_values_for_a_source_that_republishes_and_corrects_itself(tw, key):
    """S3-VA-2 S3-VA-3 S3-VA-6 S3-TF-2 (tally-wharf: an aggregator restating an old CEO with a newer Published date never
    outranks the company's page; a republished page with the same Effective replaces its earlier version)"""
    for ta in ["2020-01-01", "2021-05-31", "2021-06-01", "2021-07-01", "2022-03-01", "2022-06-01", "2024-01-01",
               "2025-01-01", "2026-02-28", "2026-03-01", "2026-03-09", "2026-03-10", "2026-03-15", "2027-01-01"]:
        check_values(tw.w.ada, TW, tw.builds, T[key], ta)


def test_tally_literal_cases(tw):
    """S3-VA-2 S3-VA-3 S3-HI-1 S3-HI-2 S3-HI-10 (a backdated correction: a page whose new version has an earlier
    Effective date replaces the later one; the entry is a correction)"""
    api = tw.w.ada
    v = lambda k, ta: ok_json(values(api, TW, ta, T[k]))["fields"]
    assert v("1", "2022-06-01")["ceo"]["value"] == "Nia Cole" and v("1", "2022-06-01")["ceo"]["true_from"] == "2022-03-01"
    assert v("2", "2022-06-01")["ceo"]["value"] == "Joe Hart" and v("2", "2022-06-01")["ceo"]["true_from"] == "2021-06-01"
    assert v("2", "2021-05-31")["ceo"]["value"] is None
    assert v("2", "2025-01-01")["funding_total"]["value"] == 12000000
    assert v("2", "2026-03-15")["funding_total"]["value"] == 30000000
    h = ok_json(tw.w.ada.get(f"/dossiers/{TW}/history"))["fields"]
    assert [(e["type"], e["value"]) for e in h["ceo"]] == [("initial", "Nia Cole"), ("correction", "Joe Hart")]
    assert [(e["type"], e["value"]) for e in h["funding_total"]] == [("initial", 12000000), ("change", 30000000)]
    feed = [e for e in ok_json(tw.w.ada.get("/changes"))["changes"] if e["domain"] == TW]
    assert [(e["field"], e["type"]) for e in feed] == [("funding_total", "change"), ("ceo", "correction")]
    got = ok_json(as_of(tw.w.ada, TW, T["1"]))
    assert got["fields"]["ceo"]["value"] == "Nia Cole" and got["fields"]["funding_total"]["value"] == 30000000


# --------------------------------------------------------------------------- tests that reset the service (last:
# they invalidate the tokens and dossiers of the module-scoped timelines above)
def test_a_dossier_whose_only_builds_failed_has_no_as_of(pworld):
    """S3-AO-8 (no build completed ready: every as_of is 404, with a valid timestamp)"""
    w = pworld
    w.mock.break_all()
    b, _ = w.build(w.ada, "orchard-lane-foods.test")
    assert b["state"] == "failed"
    err(as_of(w.ada, "orchard-lane-foods.test", "2030-01-01T00:00:00+00:00"), 404, "not_found")
    err(values(w.ada, "orchard-lane-foods.test", "2026-01-01"), 404, "not_found")
    w.mock.clear()


def test_builds_with_the_same_time_answer_with_the_last_in_build_order(pworld):
    """S3-AO-12 S3-AO-13 (two ready builds at one clock reading: as_of at that time returns the later; equivalent
    timestamps with different offsets are the same time; spent_units is the total of both)"""
    w = pworld
    d = "northwind-optics.test"
    w.mock.epoch(0)
    b0, _ = w.build(w.ada, d)
    assert b0["fields"]["ceo"]["value"] == "Mara Voss"
    w.mock.epoch(1)
    b1, _ = w.refresh(w.ada, d)                              # the clock has not moved: the same build time
    assert b1["fields"]["ceo"]["value"] == "Tomas Klein" and b1["researched_at"] == b0["researched_at"]
    t0 = "2026-03-01T09:00:00+00:00"
    got = ok_json(as_of(w.ada, d, t0))
    assert got["fields"]["ceo"]["value"] == "Tomas Klein" and got["spent_units"] == b1["spent_units"]
    assert got["fields"] == b1["fields"]
    # a third build at the same instant written with another offset
    assert_status(w.clock("2026-03-01T11:00:00+02:00"), 204)
    w.mock.epoch(0)
    b2, _ = w.refresh(w.ada, d)
    assert b2["fields"]["ceo"]["value"] == "Mara Voss"
    for ts in (t0, "2026-03-01T11:00:00+02:00", "2026-03-01T04:00:00-05:00"):
        got = ok_json(as_of(w.ada, d, ts))
        assert got["fields"]["ceo"]["value"] == "Mara Voss" and got["spent_units"] == b2["spent_units"], ts
    err(as_of(w.ada, d, "2026-03-01T08:59:59+00:00"), 404, "not_found")
    # the history carries all three builds in order (initial, then two changes for ceo)
    h = ok_json(w.ada.get(f"/dossiers/{d}/history"))["fields"]["ceo"]
    assert [e["value"] for e in h] == ["Mara Voss", "Tomas Klein", "Mara Voss"]
    assert [e["type"] for e in h][0] == "initial"
    assert all(dt(e["learned_at"]) == dt(t0) for e in h)
    # values: both builds' versions are known at as_of = t0, the later replaces the earlier (equal true_from)
    v = ok_json(values(w.ada, d, "2026-03-01", t0))["fields"]
    assert v["ceo"]["value"] == "Mara Voss"
