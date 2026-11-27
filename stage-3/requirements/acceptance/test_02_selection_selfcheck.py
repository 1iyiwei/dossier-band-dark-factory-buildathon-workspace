"""Offline checks of the stage-2 model the tests use (no service): selection rule, status, page kind
and publication time defaults, RFC 3339, and the corpus expectations. IDs: AX-6 AX-7."""
import pytest

import s2model as m


def cand(value, url="https://x.test/a", kind="own", pub=None, provider="nimble"):
    return {"value": value, "url": url, "excerpt": "e", "provider": provider, "kind": kind,
            "published_at": pub}


def order(*cs):
    return [c["value"] for c in m.derive(list(cs))["order"]]


def test_authority_recency_url_provider_value_in_that_order():
    """AX-6"""
    assert order(cand("agg", kind="aggregator", pub="2030-01-01T00:00:00Z"),
                 cand("news", kind="news", pub="2020-01-01T00:00:00Z"),
                 cand("own", kind="own", pub="2000-01-01T00:00:00Z")) == ["own", "news", "agg"]
    assert order(cand("filing", kind="filing", pub="2001-01-01T00:00:00Z"),
                 cand("own", kind="own", pub="2000-01-01T00:00:00Z")) == ["filing", "own"]   # equal authority
    assert order(cand("nopub"), cand("old", pub="1990-01-01T00:00:00Z")) == ["old", "nopub"]
    assert order(cand("b", url="https://x.test/b", pub="2020-01-01T00:00:00Z"),
                 cand("a", url="https://x.test/a", pub="2020-01-01T01:00:00+01:00")) == ["a", "b"]
    assert order(cand("up", url="https://x.test/About"), cand("low", url="https://x.test/about")) == ["up", "low"]
    assert order(cand("t", provider="tavily"), cand("n", provider="nimble"),
                 cand("k", provider="kernel"), cand("bb", provider="browserbase")) == ["n", "t", "k", "bb"]
    assert order(cand(10000000), cand(9000000)) == [9000000, 10000000]
    assert order(cand("Århus"), cand("Zagreb")) == ["Zagreb", "Århus"]
    assert order(cand("x", kind=None), cand("n", kind="news")) == ["n", "x"]     # imported: aggregator authority
    assert order(cand("a", pub="2020-01-01T00:00:00.5Z"), cand("b", pub="2020-01-01T00:00:00Z")) == ["a", "b"]


def test_status_and_citations():
    """AX-6"""
    d = m.derive([])
    assert (d["value"], d["status"], d["citations"]) == (None, "unknown", [])
    d = m.derive([cand("A", url="https://x.test/2"), cand(" A ", url="https://x.test/1")])
    assert d["status"] == "known" and [c["url"] for c in d["citations"]] == ["https://x.test/1", "https://x.test/2"]
    d = m.derive([cand("A", url="https://x.test/1"), cand("B", url="https://x.test/2", kind="news"),
                  cand("A", url="https://x.test/3", kind="aggregator")])
    assert d["status"] == "contested" and d["value"] == "A"
    assert [c["url"] for c in d["citations"]] == ["https://x.test/1", "https://x.test/3"]


def test_consistency_checker_rejects_wrong_selection_and_order():
    """AX-6"""
    good = [dict(cand("A"), retrieved_at="2026-03-01T09:00:00+00:00", selected=True)]
    fld = {"value": "A", "status": "known", "candidates": good,
           "citations": [{"url": "https://x.test/a", "excerpt": "e", "provider": "nimble"}]}
    m.check_field_consistency("ceo", fld)
    bad = dict(fld, status="contested")
    with pytest.raises(AssertionError):
        m.check_field_consistency("ceo", bad)
    two = [dict(cand("A", kind="news"), retrieved_at="2026-03-01T09:00:00+00:00", selected=True),
           dict(cand("B", kind="own"), retrieved_at="2026-03-01T09:00:00+00:00", selected=False)]
    with pytest.raises(AssertionError):
        m.check_field_consistency("ceo", {"value": "A", "status": "contested", "candidates": two,
                                          "citations": [{"url": "https://x.test/a", "excerpt": "e", "provider": "nimble"}]})


def test_page_kind_and_published_defaults():
    """AX-7"""
    k = lambda kind, url: m.page_kind(kind, url, "acme.test")
    assert k("news", "https://acme.test/x") == "news" and k("own", "https://other.test/x") == "own"
    assert k(None, "https://acme.test/x") == "own" and k(None, "https://www.acme.test/x") == "own"
    assert k(None, "https://blog.acme.test/x") == "aggregator" and k(None, "https://other.test/x") == "aggregator"
    assert k("blog", "https://acme.test/x") == "own" and k("blog", "https://other.test/x") == "aggregator"
    p = m.page_published
    assert p("2026-02-20T10:30:00+02:00") == p("2026-02-20T08:30:00Z")
    for bad in ("2026-02-20", "2026-02-20T10:30:00", "yesterday", "2026-02-30T00:00:00Z", None, ""):
        assert p(bad) is None, bad


def test_corpus_expectations_for_the_stage_2_companies_are_exact():
    """AX-7 (no fragment-only candidates: tests may assert exact sets and selection)"""
    corpus = m.load()
    for d in ("ashgrove-labs.test", "brightmoor-energy.test", "cobalt-harbor.test", "driftwood-games.test"):
        exp, _ = m.expected_candidates(d, 0, corpus)
        assert all(not e["may"] for e in exp.values()), d
    exp, _ = m.expected_candidates("brightmoor-energy.test", 0, corpus)
    assert {v for _, v in exp["funding_total"]["must"]} == {5000000}          # 7M claim unsupported
    assert {v for _, v in exp["hq_city"]["must"]} == {"Bristol"}              # served text says Leeds
    exp, _ = m.expected_candidates("brightmoor-energy.test", 0, corpus, research=False)
    assert exp["ceo"]["must"] == set()                                         # research-cited page only
