"""Stage 4 over time (prism-harbor.test, six epochs, a failed build between epochs 1 and 2): `corroborated_since` and
standing origins, executives and investors keys, investors history and feed typing, `?as_of=` and `/values` for the
eighth field. IDs (S4-*) in docstrings refer to ../LEDGER.md. Expected values: s3model.py (stage-4.md alone), and
literals derived by hand from the corpus (gen_corpus.py, prism-harbor.test)."""
import pytest

import s3model as s3
from conftest import BASE, MOCK, ok_json
from s3util import changes_all, dt, history_of, values
from s4util import EIGHT, P, PSTEPS, PT, check_keys, prism_timeline, since_of


@pytest.fixture(scope="module")
def tl():
    if not (BASE and MOCK):
        pytest.fail("BASE_URL and MOCK_URL are required")
    return prism_timeline()


def T(k):
    return dt(PT[k])


def f(tl, k, name):
    return tl.ready[k].body["fields"][name]


# --------------------------------------------------------------------------- corroborated_since
def test_every_field_carries_origins_corroborated_and_since_as_the_rules_give(tl):
    """S4-FK-1 S4-FK-2 S4-FK-3 S4-FK-4 S4-FK-5 S4-FK-7 S4-FK-8 S4-OR-8 (the model of stage-4.md Origins over the ready builds;
    candidates carry origin; a failed build changes nothing)"""
    for k, step in enumerate(tl.ready):
        check_keys(step.body["fields"], tl.corro[k], f"build {k}")
    failed = [s for s in tl.steps if s.fail][0]
    assert failed.body["state"] == "failed"
    assert failed.body["fields"] == tl.ready[1].body["fields"], "a failed build leaves the fields as they were"


def test_ceo_standing_origins_across_a_value_that_changes_and_returns(tl):
    """S4-FK-4 S4-FK-5 (literal: a second origin gathered once is standing although a later build lacks it; a new selected
    value starts with none; a value that returns starts again)"""
    me, reg, dw = "prism-harbor.test", "registry-open.test", "dealwire.test"
    want = [(["prism-harbor.test"], False, None),                       # e0 Ana Pike: the own page
            ([me, reg], True, "1"),                                      # e1: + a registry filing
            ([me], False, "1"),                                          # e2: the registry page is gone, the origin still stands
            ([me], False, None),                                         # e3 Bo Chan: a new selected value
            ([dw, me], True, "4"),                                       # e4: + an aggregator
            ([me], False, None)]                                         # e5 Ana Pike again: starts afresh
    names = ["Ana Pike", "Ana Pike", "Ana Pike", "Bo Chan", "Bo Chan", "Ana Pike"]
    for k, (og, co, since) in enumerate(want):
        fl = f(tl, k, "ceo")
        assert fl["value"] == names[k], (k, fl["value"])
        assert (fl["origins"], fl["corroborated"]) == (og, co), (k, fl["origins"], fl["corroborated"])
        assert (since_of(fl) if since else fl["corroborated_since"]) == (T(since) if since else None), (k, fl["corroborated_since"])


def test_funding_two_origins_gathered_by_different_builds_stand_together(tl):
    """S4-FK-4 S4-FK-5 S4-OR-7 (a wire page and its syndicated copy are one source; the wire origin of build 1 and the ticker
    origin of build 2 are standing origins after build 2, although no build holds both: since = build 2, corroborated false)"""
    want = [(["wirecast-daily.test"], False, None), (["wirecast-daily.test"], False, None)] + \
           [(["tickerpost.test"], False, "2")] * 4
    for k, (og, co, since) in enumerate(want):
        fl = f(tl, k, "funding_total")
        assert fl["value"] == 12000000
        assert (fl["origins"], fl["corroborated"]) == (og, co), (k, fl["origins"])
        assert (since_of(fl) if since else fl["corroborated_since"]) == (T(since) if since else None), (k, fl["corroborated_since"])


def test_executives_need_two_standing_origins_for_every_member(tl):
    """S4-FK-7 (cfo has two origins from build 1, cto from build 3 only: since = build 3; it stays while a build lacks the
    cto's second origin; a new cto member starts with none)"""
    me, reg, dw = "prism-harbor.test", "registry-open.test", "dealwire.test"
    want = [([me], False, None), ([me, reg], False, None), ([me, reg], False, None), ([dw, me, reg], True, "3"),
            ([me, reg], False, "3"), ([me, reg], False, None)]
    for k, (og, co, since) in enumerate(want):
        fl = f(tl, k, "executives")
        assert (fl["origins"], fl["corroborated"]) == (og, co), (k, fl["origins"], fl["corroborated"])
        assert (since_of(fl) if since else fl["corroborated_since"]) == (T(since) if since else None), (k, fl["corroborated_since"])
    assert f(tl, 5, "executives")["value"] == [{"title": "cfo", "name": "Cleo Dunn"}, {"title": "cto", "name": "Eli Novak"}]


def test_investors_members_and_their_standing_origins(tl):
    """S4-INV-5 S4-INV-6 S4-FK-8 (literal members per build: an own page makes a member alone; two origins make one; a wire
    page and its copy are one origin; a name leaves when its pages go)"""
    want = [(["Northwind Ventures"], ["prism-harbor.test"], False, None),
            (["Northwind Ventures"], ["prism-harbor.test"], False, None),                   # Bluebird: wire + copy, 1 origin
            (["Bluebird Capital", "Northwind Ventures"], ["dealwire.test", "prism-harbor.test", "wirecast-daily.test"], False, None),
            (["Bluebird Capital", "Cedar Capital", "Northwind Ventures"],
             ["dealwire.test", "prism-harbor.test", "registry-open.test", "wirecast-daily.test"], False, None),
            (["Bluebird Capital", "Cedar Capital"], ["dealwire.test", "registry-open.test", "wirecast-daily.test"], False, None),
            (["Bluebird Capital", "Cedar Capital", "Delta Equity"],
             ["dealwire.test", "prism-harbor.test", "registry-open.test", "tickerpost.test", "wirecast-daily.test"], True, "5")]
    for k, (val, og, co, since) in enumerate(want):
        fl = f(tl, k, "investors")
        assert fl["value"] == val and fl["status"] == "known", (k, fl["value"])
        assert (fl["origins"], fl["corroborated"]) == (og, co), (k, fl["origins"], fl["corroborated"])
        assert (since_of(fl) if since else fl["corroborated_since"]) == (T(since) if since else None), (k, fl["corroborated_since"])
    b = f(tl, 1, "investors")
    assert "Bluebird Capital" in {c["value"] for c in b["candidates"]}
    assert [c["selected"] for c in b["candidates"] if c["value"] == "Bluebird Capital"] == [False, False]


# --------------------------------------------------------------------------- investors history and feed
def test_investors_history_is_typed_by_name(tl):
    """S4-INV-12 S4-INV-1 (a name added with an earlier true_from than the old value: correction; a name added later: change;
    a name leaving: change; the first value: initial)"""
    h = history_of(tl.w.ada, P)
    assert list(h["fields"]) == list(EIGHT)
    got = h["fields"]["investors"]
    assert [e["type"] for e in got] == ["initial", "change", "correction", "change", "change"]
    assert [e["value"] for e in got] == [["Northwind Ventures"], ["Bluebird Capital", "Northwind Ventures"],
                                         ["Bluebird Capital", "Cedar Capital", "Northwind Ventures"],
                                         ["Bluebird Capital", "Cedar Capital"],
                                         ["Bluebird Capital", "Cedar Capital", "Delta Equity"]]
    assert [e["true_from"] for e in got] == ["2024-05-02", "2025-02-01", "2025-02-01", "2025-02-01", "2026-01-01"]
    assert [dt(e["learned_at"]) for e in got] == [T("0"), T("2"), T("3"), T("4"), T("5")]
    for e in got:
        assert e["citations"] and all(set(c) >= {"url", "excerpt", "provider"} for c in e["citations"])
    for name in EIGHT:
        assert [(e["type"], e["value"], e["true_from"]) for e in h["fields"][name]] == \
               [(x["type"], x["value"], x["true_from"]) for x in tl.hist[name]], name


def test_the_feed_numbers_the_entries_of_one_build_with_investors_last(tl):
    """S4-INV-1 S4-INV-12 S4-OP-5 (investors entries are change/correction by name, from/to are the arrays; the entries of one
    build are numbered in the order of the eight fields; no entry twice or missing)"""
    got = changes_all(tl.w.ada)
    assert len(got) == len(tl.feed), [(e["field"], e["type"]) for e in got]
    seqs = [e["seq"] for e in got]
    assert seqs == sorted(set(seqs))
    for e, x in zip(got, tl.feed):
        _, fld_, typ, old, new, tf, when = x
        assert (e["domain"], e["field"], e["type"], e["from"], e["to"], e["true_from"]) == (P, fld_, typ, old, new, tf), (e, x)
        assert dt(e["learned_at"]) == when
    inv = [e for e in got if e["field"] == "investors"]
    assert [e["type"] for e in inv] == ["change", "correction", "change", "change"]
    assert inv[0]["from"] == ["Northwind Ventures"] and inv[0]["to"] == ["Bluebird Capital", "Northwind Ventures"]
    for build in set(dt(e["learned_at"]) for e in got):
        order = [EIGHT.index(e["field"]) for e in got if dt(e["learned_at"]) == build]
        assert order == sorted(order), "the entries one build adds are numbered in field order, investors last"


# --------------------------------------------------------------------------- as_of and values
def test_as_of_answers_carry_the_keys_of_the_build_they_describe(tl):
    """S4-FK-9 S4-UP-2 (`?as_of=` returns the eight fields of the build: origins, corroborated and corroborated_since as that
    build's response had them, using no later builds)"""
    for k, step in enumerate(tl.ready):
        j = ok_json(tl.w.ada.get(f"/dossiers/{P}", params={"as_of": PT[step.key]}))
        assert list(j["fields"]) == list(EIGHT)
        assert j["fields"] == step.body["fields"], f"as_of build {k}"
        check_keys(j["fields"], tl.corro[k], f"as_of {k}")
    j = ok_json(tl.w.ada.get(f"/dossiers/{P}", params={"as_of": "2026-06-15T00:00:00+00:00"}))
    assert j["fields"] == tl.ready[3].body["fields"]


@pytest.mark.parametrize("true_at,as_of_k", [("2023-06-01", "5"), ("2024-06-01", "5"), ("2025-06-01", "5"),
                                             ("2025-06-01", "2"), ("2026-02-01", "5"), ("2022-01-01", "5")])
def test_values_for_investors_decide_membership_from_the_candidates_at_true_at(tl, true_at, as_of_k):
    """S4-INV-11 S4-INV-1 (`/values`: the eighth field's value, true_from and citations from the candidates at true_at and as_of)"""
    j = ok_json(values(tl.w.ada, P, true_at, PT[as_of_k]))
    assert list(j["fields"]) == list(EIGHT)
    exp = s3.values_at(tl.builds, dt(PT[as_of_k]), true_at)
    for name in EIGHT:
        fl = j["fields"][name]
        assert (fl["value"], fl["true_from"]) == (exp[name]["value"], exp[name]["true_from"]), (name, fl, exp[name])
        assert [c["url"] for c in fl["citations"]] == exp[name]["urls"], name
        assert set(fl) >= {"value", "true_from", "citations"}
    if true_at == "2022-01-01":
        assert j["fields"]["investors"]["value"] is None and j["fields"]["investors"]["citations"] == []


def test_values_before_a_names_pages_hold_leave_it_out(tl):
    """S4-INV-11 (Cedar Capital's registry page holds from 2023-01-01 and is a filing: a member alone; Bluebird needs two
    origins: wire and aggregator, both holding from 2025-02-01)"""
    for ta, want in (("2024-01-01", ["Cedar Capital"]), ("2025-03-01", ["Bluebird Capital", "Cedar Capital", "Northwind Ventures"])):
        j = ok_json(values(tl.w.ada, P, ta, PT["3"]))
        assert j["fields"]["investors"]["value"] == want, (ta, j["fields"]["investors"])
