"""Stage 3: two times per value, history and the change feed over the meridian-ledger timeline
(five epochs of the web, one failed build between them; gen_corpus.py stage-3 section).
IDs (S3-*) in docstrings refer to ../LEDGER.md.

Literal expectations below come from stage-3.md read by hand, not from the service; s3model.py is the
independent model they are also compared with (test_03_model_selfcheck.py checks the model)."""
import pytest

import s2model as m
import s3model as s3
from conftest import BASE, MOCK, Api, assert_status, err, ok_json, parse_ts
from s3util import M, EIGHT, T, changes_all, dt, history_of, run_timeline

TYPES = {"legal_name": [], "hq_city": [], "founded_year": ["change"], "headcount_range": ["initial"],
         "funding_total": [], "ceo": ["initial", "change", "correction", "change", "change"],
         "executives": ["initial", "change", "change", "correction", "change"]}
# true_from of the selected value after each ready build (b0 b1 b2 b3 b4)
TF = {"ceo": ["2021-04-01", "2026-03-20", "2026-01-01", None, None],
      "headcount_range": ["2020-01-01", "2020-01-01", "2019-06-01", "2020-01-01", "2020-01-01"],
      "founded_year": [None, None, "2026-04-01", "2026-04-01", "2026-04-01"],
      "executives": ["2025-09-01", "2026-03-20", "2025-12-01", "2025-10-01", "2025-09-01"]}
# learned_at (key of T) of the selected value after each ready build: the build that made it selected
LA = {"ceo": ["0", "1", "2", None, "4"], "headcount_range": ["0"] * 5,
      "founded_year": [None, None, "2", "2", "2"], "executives": ["0", "1", "2", "3", "4"]}


@pytest.fixture(scope="module")
def tl():
    if not (BASE and MOCK):
        pytest.fail("BASE_URL and MOCK_URL are required")
    return run_timeline()


def fld(tl, k, name):
    return tl.ready[k].body["fields"][name]


# --------------------------------------------------------------------------- two times per value
def test_selected_values_follow_the_evidence_of_each_epoch(tl):
    """S3-TF-6 S3-TF-8 S3-EX-3 S3-EX-11 (true_from of the selected value is the selected candidate's; the field's
    value, status and citations follow from the candidates; literal true_from per build)"""
    for k, step in enumerate(tl.ready):
        st = tl.builds[k].state()
        for name in EIGHT:
            f = step.body["fields"][name]
            assert f["value"] == st[name]["value"], (k, name)
            assert f["status"] == st[name]["status"], (k, name)
            assert f["true_from"] == st[name]["true_from"], (k, name, f["true_from"])
            assert [c["url"] for c in f["citations"]] == st[name]["urls"], (k, name)
            if name in TF:
                assert f["true_from"] == TF[name][k], (k, name)
        for name in ("legal_name", "hq_city", "funding_total"):
            assert step.body["fields"][name]["status"] == "unknown"
    assert fld(tl, 0, "ceo")["status"] == "contested" and fld(tl, 3, "ceo")["status"] == "unknown"
    assert fld(tl, 3, "ceo")["value"] is None and fld(tl, 3, "ceo")["true_from"] is None \
        and fld(tl, 3, "ceo")["learned_at"] is None
    assert fld(tl, 4, "ceo")["value"] == "Dana Ruiz" and fld(tl, 4, "ceo")["true_from"] is None


def test_candidates_carry_true_from_and_learned_at(tl):
    """S3-TF-4 S3-TF-5 S3-EX-10 (retrieved_at is the build's time; learned_at is the time of the first build whose
    candidate set held the same field, value, URL and provider; candidates carry the page's true_from)"""
    seen = {}                                   # (name, value, url, provider) -> time of first build
    for k, step in enumerate(tl.ready):
        for name in EIGHT:
            for c in step.body["fields"][name]["candidates"]:
                ident = (name, c.get("title"), c["value"], c["url"], c["provider"])
                seen.setdefault(ident, step.time)
        for name in EIGHT:
            for c in step.body["fields"][name]["candidates"]:
                ident = (name, c.get("title"), c["value"], c["url"], c["provider"])
                assert dt(c["retrieved_at"]) == step.time, (k, name, "retrieved_at")
                assert dt(c["learned_at"]) == seen[ident], \
                    f"build {k} {name} {c['value']!r}: learned_at {c['learned_at']} != first build {seen[ident]}"
    # the unchanged team page keeps its learned_at while retrieved_at moves with every build
    for k, step in enumerate(tl.ready):
        c = step.body["fields"]["headcount_range"]["candidates"][0]
        assert dt(c["learned_at"]) == dt(T["0"]) and dt(c["retrieved_at"]) == step.time


def test_selected_learned_at_is_the_build_that_made_it_selected(tl):
    """S3-TF-7 S3-TF-8 (literal per build; same value in a later build keeps its learned_at)"""
    for k, step in enumerate(tl.ready):
        for name, keys in LA.items():
            f = step.body["fields"][name]
            if keys[k] is None:
                assert f["learned_at"] is None and f["status"] == "unknown", (k, name)
            else:
                assert dt(f["learned_at"]) == dt(T[keys[k]]), (k, name, f["learned_at"])


def test_same_value_with_other_dates_adds_nothing_but_moves_true_from(tl):
    """S3-HI-6 S3-TF-6 (build 2 serves the same headcount with an earlier Effective: the dossier's true_from is the
    new candidate's, learned_at stays, and the history has still only its initial entry)"""
    f2 = fld(tl, 2, "headcount_range")
    assert f2["value"] == "51-200" and f2["true_from"] == "2019-06-01" and dt(f2["learned_at"]) == dt(T["0"])
    h = history_of(tl.w.ada, M)["fields"]["headcount_range"]
    assert len(h) == 1 and h[0]["type"] == "initial" and h[0]["true_from"] == "2020-01-01"
    assert dt(h[0]["learned_at"]) == dt(T["0"])


# --------------------------------------------------------------------------- history
def test_history_lists_every_field_in_the_order_the_entries_were_added(tl):
    """S3-HI-1 S3-HI-2 S3-HI-3 S3-HI-4 S3-HI-5 S3-HI-7 S3-HI-8 (all seven fields, oldest first, entry value/
    true_from/learned_at/citations are those of the selected value it records; typed initial/change/correction)"""
    h = history_of(tl.w.ada, M)
    assert set(h) == {"domain", "fields"} and h["domain"] == M
    assert list(h["fields"]) == list(EIGHT)
    for name in EIGHT:
        got = h["fields"][name]
        assert [e["type"] for e in got] == TYPES[name], (name, [e["type"] for e in got])
        exp = tl.hist[name]
        assert len(got) == len(exp), name
        for e, x in zip(got, exp):
            assert set(e) >= {"type", "value", "true_from", "learned_at", "citations"}, sorted(e)
            assert e["type"] == x["type"] and e["value"] == x["value"], (name, e, x)
            assert e["true_from"] == x["true_from"], (name, e["type"], e["true_from"], x["true_from"])
            assert dt(e["learned_at"]) == x["learned_at"], (name, e["learned_at"])
            assert [c["url"] for c in e["citations"]] == x["urls"], (name, e["citations"])
            for c in e["citations"]:
                assert set(c) >= {"url", "excerpt", "provider"}


def test_each_entry_records_the_selected_value_as_the_build_returned_it(tl):
    """S3-HI-4 S3-HI-5 (value, true_from, learned_at and citations of an entry equal the dossier's field right after
    the build that added it; a value that disappears is an entry with null value, true_from null, no citations)"""
    h = history_of(tl.w.ada, M)["fields"]
    for name in EIGHT:
        entries = iter(h[name])
        e = next(entries, None)
        prev = None
        for k, step in enumerate(tl.ready):
            f = step.body["fields"][name]
            cur = f["value"]
            if (k == 0 and cur is None) or (k > 0 and cur == prev):
                prev = cur
                continue
            assert e is not None, (name, k, "entry missing")
            assert e["value"] == cur and dt(e["learned_at"]) == step.time, (name, k, e)
            assert e["true_from"] == f["true_from"], (name, k)
            assert e["citations"] == f["citations"], (name, k)
            if cur is None:
                assert e["true_from"] is None and e["citations"] == []
            prev = cur
            e = next(entries, None)
        assert e is None, (name, "extra history entries", e)


def test_the_first_value_of_a_field_is_initial_and_later_first_values_are_changes(tl):
    """S3-HI-3 S3-HI-9 (a field's first selected value, set by the first ready build, is initial; a field unknown
    after that build gets a change when it first gets a value; fields that never get a value have no entries)"""
    h = history_of(tl.w.ada, M)["fields"]
    assert h["ceo"][0]["type"] == "initial" and h["ceo"][0]["value"] == "Dana Ruiz"
    assert h["founded_year"][0]["type"] == "change" and h["founded_year"][0]["value"] == 2003
    assert dt(h["founded_year"][0]["learned_at"]) == dt(T["2"]) and h["founded_year"][0]["true_from"] == "2026-04-01"
    assert h["hq_city"] == [] and h["legal_name"] == [] and h["funding_total"] == []


def test_corrections_and_changes_by_true_from(tl):
    """S3-HI-1 S3-HI-2 S3-HI-10 (new true_from on or before the earlier one -> correction; later, appearing,
    disappearing or null true_from -> change)"""
    ceo = history_of(tl.w.ada, M)["fields"]["ceo"]
    assert [(e["value"], e["true_from"], e["type"]) for e in ceo] == [
        ("Dana Ruiz", "2021-04-01", "initial"), ("Lee Park", "2026-03-20", "change"),
        ("Sam Ortiz", "2026-01-01", "correction"),          # 2026-01-01 is before 2026-03-20
        (None, None, "change"),                             # the value disappears
        ("Dana Ruiz", None, "change")]                      # true_from null: never a correction


def test_failed_builds_add_nothing(tl):
    """S3-HI-11 (the failed build between builds 1 and 2: no entry, fields and candidates as they were)"""
    failed = [s for s in tl.steps if s.fail][0]
    before = tl.ready[1].body
    assert failed.body["state"] == "failed" and failed.body["fields"] == before["fields"]
    assert failed.body["researched_at"] == before["researched_at"]
    h = history_of(tl.w.ada, M)["fields"]
    assert all(dt(e["learned_at"]) != failed.time for f in h.values() for e in f)
    assert all(dt(c["learned_at"]) != failed.time for c in changes_all(tl.w.ada))


def test_history_of_unknown_domain_and_path_normalisation(tl):
    """S3-HI-12 (404 not_found; the domain in the path is normalised; authentication required)"""
    err(tl.w.ada.get("/dossiers/nobody-here.test/history"), 404, "not_found")
    assert history_of(tl.w.ada, "WWW.Meridian-Ledger.TEST.") == history_of(tl.w.ada, M)
    err(Api(BASE).get(f"/dossiers/{M}/history"), 401, "unauthenticated")
    err(tl.w.ada.get("/dossiers/not_a_domain/history"), 422, "validation_failed")


# --------------------------------------------------------------------------- feed
def expect_feed(tl):
    return [{"domain": M, "field": f, "type": typ, "from": old, "to": new, "true_from": tf,
             "learned_at": t} for (_, f, typ, old, new, tf, t) in tl.feed]


def test_the_feed_holds_every_change_and_correction_once_in_field_order(tl):
    """S3-FD-1 S3-FD-2 S3-FD-3 S3-FD-4 S3-HI-13 (entries of one build in the order of the fields, then executives; from/to
    the earlier and new value, true_from the new value's, learned_at the build's time; no initial entries)"""
    got = changes_all(tl.w.ada)
    exp = expect_feed(tl)
    assert [(e["field"], e["type"]) for e in got] == [
        ("ceo", "change"), ("executives", "change"),                                   # build 1
        ("ceo", "correction"), ("founded_year", "change"), ("executives", "change"),   # build 2
        ("ceo", "change"), ("executives", "correction"),                               # build 3
        ("ceo", "change"), ("executives", "change")]                                   # build 4
    assert len(got) == len(exp) == 9
    seqs = [e["seq"] for e in got]
    assert all(isinstance(s, int) and not isinstance(s, bool) and s > 0 for s in seqs)
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), seqs
    for e, x in zip(got, exp):
        assert set(e) == {"seq", "domain", "field", "type", "from", "to", "true_from", "learned_at"}, sorted(e)
        assert (e["domain"], e["field"], e["type"], e["from"], e["to"], e["true_from"]) == \
               (x["domain"], x["field"], x["type"], x["from"], x["to"], x["true_from"]), (e, x)
        assert dt(e["learned_at"]) == x["learned_at"]
    assert got[0]["from"] == "Dana Ruiz" and got[0]["to"] == "Lee Park" and got[0]["true_from"] == "2026-03-20"
    assert got[5]["to"] is None and got[5]["true_from"] is None          # a value disappearing
    assert got[7]["from"] is None and got[7]["to"] == "Dana Ruiz"        # one appearing, true_from null
    assert got[3]["from"] is None and got[3]["to"] == 2003


def test_feed_entries_agree_with_history(tl):
    """S3-FD-5 (every change/correction entry of the history is one feed entry with the same value, true_from,
    learned_at; the number of entries matches exactly: none twice, none missing)"""
    h = history_of(tl.w.ada, M)["fields"]
    hist_entries = sorted(((dt(e["learned_at"]), EIGHT.index(f), e["type"], repr(e["value"]), e["true_from"])
                           for f, es in h.items() for e in es if e["type"] != "initial"),
                          key=lambda t: (t[0], t[1]))
    feed = sorted(((dt(e["learned_at"]), EIGHT.index(e["field"]), e["type"], repr(e["to"]), e["true_from"])
                   for e in changes_all(tl.w.ada)), key=lambda t: (t[0], t[1]))
    assert feed == hist_entries


def test_the_feed_pages_by_since_and_limit(tl):
    """S3-FD-6 S3-FD-7 S3-FD-8 (since lists seq greater than it, ascending; limit default 50, 1..200; has_more)"""
    api = tl.w.ada
    full = ok_json(api.get("/changes"))
    assert full["has_more"] is False and len(full["changes"]) == 9
    seqs = [e["seq"] for e in full["changes"]]
    p = ok_json(api.get("/changes", params={"limit": 4}))
    assert [e["seq"] for e in p["changes"]] == seqs[:4] and p["has_more"] is True
    p = ok_json(api.get("/changes", params={"since": seqs[3], "limit": 5}))
    assert [e["seq"] for e in p["changes"]] == seqs[4:9] and p["has_more"] is False
    p = ok_json(api.get("/changes", params={"since": seqs[3], "limit": 4}))
    assert [e["seq"] for e in p["changes"]] == seqs[4:8] and p["has_more"] is True
    p = ok_json(api.get("/changes", params={"since": seqs[-1]}))
    assert p == {"changes": [], "has_more": False}
    p = ok_json(api.get("/changes", params={"since": seqs[-1] + 1000}))
    assert p == {"changes": [], "has_more": False}
    p = ok_json(api.get("/changes", params={"since": 0, "limit": 1}))
    assert len(p["changes"]) == 1 and p["has_more"] is True
    p = ok_json(api.get("/changes", params={"limit": 200, "unknown": "x"}))     # unknown parameters are ignored
    assert len(p["changes"]) == 9


@pytest.mark.parametrize("params", [{"since": "-1"}, {"since": "abc"}, {"since": "1.5"}, {"since": "1e2"},
                                    {"since": "+3"}, {"since": ""}, {"limit": "0"}, {"limit": "201"},
                                    {"limit": "-5"}, {"limit": "x"}, {"limit": "4.0"}, {"limit": ""}])
def test_feed_parameter_validation(tl, params):
    """S3-FD-9 (since an integer 0 or more, limit 1 to 200, plain decimal digits: otherwise 422 validation_failed)"""
    err(tl.w.ada.get("/changes", params=params), 422, "validation_failed")


def test_feed_requires_authentication(tl):
    """S3-FD-10"""
    err(Api(BASE).get("/changes"), 401, "unauthenticated")
    err(Api(BASE).get(f"/dossiers/{M}/values", params={"true_at": "2026-01-01"}), 401, "unauthenticated")
    err(Api(BASE).get(f"/dossiers/{M}", params={"as_of": "2026-04-01T00:00:00+00:00"}), 401, "unauthenticated")


def test_executives_entries_are_typed_by_title(tl):
    """S3-EX-13 (a title differs when exactly one value has it or the names differ; correction only when every
    differing title has both members, both true_from set, the new on or before the earlier)"""
    feed = [e for e in changes_all(tl.w.ada) if e["field"] == "executives"]
    assert [e["type"] for e in feed] == ["change", "change", "correction", "change"]
    # build 1: cto Ben Okafor -> Cho Min, later true_from: change
    assert feed[0]["from"] == [{"title": "cfo", "name": "Ana Silva"}, {"title": "cto", "name": "Ben Okafor"}]
    assert feed[0]["to"] == [{"title": "cfo", "name": "Ana Silva"}, {"title": "cto", "name": "Cho Min"}]
    assert feed[0]["true_from"] == "2026-03-20"
    # build 2: coo appears (exactly one value has it): change, members in the order cfo, coo, cto
    assert [x["title"] for x in feed[1]["to"]] == ["cfo", "coo", "cto"] and feed[1]["true_from"] == "2025-12-01"
    # build 3: only cto differs, earlier true_from (2025-10-01 <= 2025-12-01): correction
    assert feed[2]["from"][2] == {"title": "cto", "name": "Cho Min"} and feed[2]["to"][2]["name"] == "Eli Novak"
    assert feed[2]["true_from"] == "2025-10-01"
    # build 4: cto differs with an earlier true_from but coo disappears: change
    assert [x["title"] for x in feed[3]["to"]] == ["cfo", "cto"] and feed[3]["to"][1]["name"] == "Fay Quinn"
    h = history_of(tl.w.ada, M)["fields"]["executives"]
    assert [e["type"] for e in h] == ["initial", "change", "change", "correction", "change"]
    assert h[0]["value"] == [{"title": "cfo", "name": "Ana Silva"}, {"title": "cto", "name": "Ben Okafor"}]
    assert h[0]["true_from"] == "2025-09-01"
