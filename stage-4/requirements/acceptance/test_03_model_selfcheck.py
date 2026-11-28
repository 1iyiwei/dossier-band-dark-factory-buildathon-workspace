"""Offline checks (no service) of the stage-3 model (s3model.py) against stage-3.md read by hand, and of the stage-3
corpus (gen_corpus.py) against the model. IDs (AX-*) in ../LEDGER.md."""
from datetime import datetime, timezone

import pytest

import oracle as o
import s2model as m
import s3model as s3
from conftest import CORPUS_S2

D = lambda s: datetime.fromisoformat(s)


def test_true_from_of_a_page():
    """AX-8 (Two times per value: Effective, else UTC date of published_at, else null)"""
    assert s3.page_true_from("2026-01-05", "2026-02-01T00:00:00Z") == "2026-01-05"
    assert s3.page_true_from(None, "2026-02-10T23:30:00-05:00") == "2026-02-11"
    assert s3.page_true_from("2026-02-30", "2026-03-01T00:30:00+02:00") == "2026-02-28"
    assert s3.page_true_from("2026-3-1", None) is None and s3.page_true_from("x", "garbage") is None
    assert s3.page_true_from("2024-02-29", None) == "2024-02-29"
    assert s3.page_true_from("2023-02-29", "2026-03-09T12:00:00Z") == "2026-03-09"
    assert s3.page_true_from("2026-01-05T00:00:00Z", "2026-03-10T00:00:00Z") == "2026-03-10"


def test_classification_of_changes():
    """AX-8 (change/correction table and the executives typing)"""
    c = s3.classify_field
    assert c(("a", "2026-03-20"), ("b", "2026-03-20")) == "correction"      # on or before
    assert c(("a", "2026-03-20"), ("b", "2026-01-01")) == "correction"
    assert c(("a", "2026-03-20"), ("b", "2026-04-01")) == "change"
    assert c(("a", None), ("b", "2026-01-01")) == "change" and c(("a", "2026-03-20"), ("b", None)) == "change"
    assert c((None, None), ("b", "2026-01-01")) == "change" and c(("a", "2026-03-20"), (None, None)) == "change"
    mem = lambda *t: [{"title": a, "name": b, "true_from": f} for a, b, f in t]
    e = s3.classify_exec
    assert e(mem(("cto", "A", "2026-03-01")), mem(("cto", "B", "2026-02-01"))) == "correction"
    assert e(mem(("cto", "A", "2026-03-01")), mem(("cto", "B", "2026-04-01"))) == "change"
    assert e(mem(("cto", "A", None)), mem(("cto", "B", "2026-02-01"))) == "change"
    assert e(mem(("cfo", "X", "2026-03-01"), ("cto", "A", "2026-03-01")),
             mem(("cfo", "X", "2026-01-01"), ("cto", "B", "2026-02-01"))) == "correction"   # only cto differs
    assert e(mem(("cto", "A", "2026-03-01")), mem(("cto", "A", "2026-03-01"), ("coo", "C", "2026-01-01"))) == "change"
    assert e(mem(("cto", "A", "2026-03-01"), ("coo", "C", "2026-03-01")), mem(("cto", "B", "2026-01-01"))) == "change"


def mk(t, **pages):
    """a build whose pages hold the given (true_from, ceo name or None)"""
    pg = {}
    for url, (tf, name) in pages.items():
        cands = [{"value": name, "url": url, "excerpt": "", "provider": "nimble", "kind": "own",
                  "published_at": "2026-01-01T00:00:00+00:00", "true_from": tf}] if name else []
        pg[url] = (tf, {"ceo": cands} if cands else {})
    return s3.Build(D(t), pg)


def test_page_version_rules():
    """AX-8 (the replace/end rules of `values`: replaced on or after; the latest survivor ends; null holds from no date)"""
    b = [mk("2026-01-01T00:00:00+00:00", u=("2021-04-01", "A")),
         mk("2026-02-01T00:00:00+00:00", u=("2026-03-20", "B")),
         mk("2026-03-01T00:00:00+00:00", u=("2026-01-01", "C"))]
    ceo = lambda ts, ta: s3.values_at(b, D(ts), ta)["ceo"]["value"]
    assert ceo("2026-01-15T00:00:00+00:00", "2021-04-01") == "A" and ceo("2026-01-15T00:00:00+00:00", "2021-03-31") is None
    assert ceo("2026-02-15T00:00:00+00:00", "2026-03-19") == "A" and ceo("2026-02-15T00:00:00+00:00", "2026-03-20") == "B"
    assert ceo("2026-03-15T00:00:00+00:00", "2026-03-25") == "C" and ceo("2026-03-15T00:00:00+00:00", "2025-12-31") == "A"
    # a version with no candidates ends the earlier one; a null true_from replaces everything
    b.append(mk("2026-04-01T00:00:00+00:00", u=("2026-05-01", None)))
    assert s3.values_at(b, D("2026-04-15T00:00:00+00:00"), "2026-05-01")["ceo"]["value"] is None
    assert s3.values_at(b, D("2026-04-15T00:00:00+00:00"), "2026-04-30")["ceo"]["value"] == "C"
    b.append(mk("2026-05-01T00:00:00+00:00", u=(None, "D")))
    for ta in ("2021-04-01", "2026-01-01", "2030-01-01"):
        assert s3.values_at(b, D("2026-06-01T00:00:00+00:00"), ta)["ceo"]["value"] is None
    # equal true_from: the later version replaces the earlier
    b = [mk("2026-01-01T00:00:00+00:00", u=("2026-01-01", "A")), mk("2026-02-01T00:00:00+00:00", u=("2026-01-01", "B"))]
    assert s3.values_at(b, D("2026-02-01T00:00:00+00:00"), "2026-01-01")["ceo"]["value"] == "B"
    assert s3.values_at(b, D("2026-01-15T00:00:00+00:00"), "2026-01-01")["ceo"]["value"] == "A"
    # a page that is not gathered again never ends
    b = [mk("2026-01-01T00:00:00+00:00", u=("2020-01-01", "A")), mk("2026-02-01T00:00:00+00:00", v=("2020-01-01", "Z"))]
    assert s3.values_at(b, D("2026-03-01T00:00:00+00:00"), "2030-01-01")["ceo"]["value"] in ("A", "Z")
    assert s3.as_of_build(b, D("2026-01-15T00:00:00+00:00")) == 0 and s3.as_of_build(b, D("2025-01-01T00:00:00+00:00")) is None


def test_the_specification_example_of_executives():
    """AX-8 (stage-3.md Executives example: cfo and cto members, citations in member order, true_from the latest)"""
    c = lambda t, v, u, tf, kind="own": {"value": v, "url": u, "excerpt": "", "provider": "nimble", "kind": kind,
                                         "published_at": "2026-01-01T00:00:00+00:00", "true_from": tf}
    e = s3.exec_of({"cfo": [c("cfo", "Ana Silva", "https://acme-robotics.test/team", "2025-09-01")],
                    "cto": [c("cto", "Ben Okafor", "https://bizdata.test/acme-robotics", "2025-08-01", "aggregator")]})
    assert e["value"] == [{"title": "cfo", "name": "Ana Silva"}, {"title": "cto", "name": "Ben Okafor"}]
    assert e["status"] == "known" and e["true_from"] == "2025-09-01"
    assert [x["url"] for x in e["citations"]] == ["https://acme-robotics.test/team", "https://bizdata.test/acme-robotics"]
    e = s3.exec_of({"cto": [c("cto", "Ben Okafor", "u", None)], "cfo": [c("cfo", "Ana Silva", "v", "2025-09-01")]})
    assert e["true_from"] is None and [x["title"] for x in e["value"]] == ["cfo", "cto"]
    assert s3.exec_of({})["value"] is None and s3.exec_of({})["status"] == "unknown"
    two = s3.exec_of({"cfo": [c("cfo", "A One", "https://x.test/a", "2025-01-01"),
                              c("cfo", "B Two", "https://y.test/a", "2025-01-01", "aggregator")]})
    assert two["status"] == "contested" and two["value"] == [{"title": "cfo", "name": "A One"}]


def test_meridian_timeline_model_matches_the_hand_derived_literals():
    """AX-8 AX-9 (the corpus company of the timeline tests: types of history and feed entries per field; exact candidates)"""
    times = ["2026-03-01T09:00:00+00:00", "2026-04-01T09:00:00+00:00", "2026-05-01T09:00:00+00:00",
             "2026-06-01T09:00:00+00:00", "2026-07-01T09:00:00+00:00"]
    builds = [s3.build_from_epoch("meridian-ledger.test", e, D(times[e]), CORPUS_S2) for e in range(5)]
    hist, feed = s3.history(builds)
    assert {f: [e["type"] for e in es] for f, es in hist.items()} == {
        "legal_name": [], "hq_city": [], "founded_year": ["change"], "headcount_range": ["initial"], "funding_total": [],
        "ceo": ["initial", "change", "correction", "change", "change"],
        "executives": ["initial", "change", "change", "correction", "change"]}
    assert [(b, f, t) for b, f, t, *_ in feed] == [
        (1, "ceo", "change"), (1, "executives", "change"), (2, "ceo", "correction"), (2, "founded_year", "change"),
        (2, "executives", "change"), (3, "ceo", "change"), (3, "executives", "correction"), (4, "ceo", "change"),
        (4, "executives", "change")]
    assert [e["true_from"] for e in hist["ceo"]] == ["2021-04-01", "2026-03-20", "2026-01-01", None, None]
    # no fragment-only candidates: exact for the timeline companies
    for dom in ("meridian-ledger.test", "ember-dates.test", "tally-wharf.test", "keystone-yards.test") + tuple(
            f"fleet-{n}.test" for n in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")):
        for ep in range(5):
            res, info, _ = s3.expected_all(dom, ep, CORPUS_S2)
            assert all(not v["may"] for v in res.values()), (dom, ep)


def test_corpus_executive_designs():
    """AX-9 (executive sentences of the stage-3 corpus read as designed by Appendix A with the title phrases)"""
    res, info, _ = s3.expected_all("paxton-quay.test", 0, CORPUS_S2)
    assert {u.rsplit("/", 1)[1] + ":" + v for u, v in res["cfo"]["must"]} == {"people:Iris Holt", "paxton-quay:Walt Moss"}
    assert {v for _, v in res["coo"]["must"]} == {"Rhea Cho"} and {v for _, v in res["cto"]["must"]} == {"Yan Li Wu"}
    assert res["ceo"]["must"] == set()
    dom = "paxton-quay.test"
    for s, f in (("Paxton Quay CEO Dana Reyes and CFO Tom Wells joined in 2019.", "cfo"),
                 ("Former CFO Walt Moss left Paxton Quay in 2020.", "cfo"),
                 ("Paxton Quay will become a public company and its COO Sara Lund will lead the listing.", "coo"),
                 ("Paxton Quay is advised by Brightline Partners, whose CFO is Tom Wells.", "cfo")):
        assert o.supported_values(s, f, dom) == set(), s
