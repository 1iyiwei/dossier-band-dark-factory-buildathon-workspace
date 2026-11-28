"""Stage 3: executives and the true_from of a page. IDs (S3-*) in docstrings refer to ../LEDGER.md.
Companies (gen_corpus.py stage-3 section): ember-dates.test (every shape of Effective/Published),
paxton-quay.test (executive sentences that must not give a person; contested cfo, six fields uncontested),
meridian-ledger.test (research run with executives in the dossier), northwind-optics.test (no executives)."""
from types import SimpleNamespace

import pytest

import oracle as o
import s2model as m
import s3model as s3
from conftest import (BASE, FIELDS, MOCK, MOCK_TOKEN, UNKNOWN, Mock, World, check_build, ok_json,
                      successful, CORPUS_S2, check_shape, six)
from s3util import dt

EMB, PAX, MER, NW = "ember-dates.test", "paxton-quay.test", "meridian-ledger.test", "northwind-optics.test"


@pytest.fixture(scope="module")
def sc():
    if not (BASE and MOCK):
        pytest.fail("BASE_URL and MOCK_URL are required")
    mock = Mock(MOCK, MOCK_TOKEN)
    w = World(mock)
    w.reset()
    out = SimpleNamespace(w=w, bodies={}, windows={})
    for d in (EMB, PAX, MER, NW):
        out.bodies[d], out.windows[d] = w.build(w.ada, d)
        assert out.bodies[d]["state"] == "ready", d
    return out


# --------------------------------------------------------------------------- true_from of a page
EMBER = {"a": "2026-01-05",       # Effective wins over Published
         "b": "2026-02-11",       # no Effective: the UTC date of 2026-02-10T23:30:00-05:00
         "c": "2026-02-28",       # Effective 2026-02-30 is not a date: UTC date of 2026-03-01T00:30:00+02:00
         "d": None,               # Effective is not a date, no Published
         "e": None,               # no Effective, Published is not an RFC 3339 timestamp
         "f": "2026-03-05",       # Effective 2026-3-1 is not YYYY-MM-DD
         "g": "2024-02-29",       # a real leap day, no Published
         "h": "2026-03-09",       # Effective 2023-02-29 is not a date
         "i": "2026-03-10",       # a timestamp is not a YYYY-MM-DD date
         "j": "2026-04-02"}       # Effective wins even over a Published of another day


def test_true_from_follows_effective_then_published_in_utc(sc):
    """S3-TF-1 S3-TF-2 S3-TF-3 S3-TF-4 S3-TF-10 (every candidate carries its page's true_from: the Effective date when valid,
    else the UTC date part of Published, else null; the selected value's is its selected candidate's)"""
    b = sc.bodies[EMB]
    check_build(b, sc.windows[EMB])
    f = b["fields"]["founded_year"]
    got = {c["url"].rsplit("/", 1)[1]: c["true_from"] for c in f["candidates"]}
    assert got == EMBER, got
    assert len(f["candidates"]) == 10 and f["status"] == "contested"
    assert f["value"] == 2010 and f["true_from"] == "2026-04-02"      # latest Published ranks first
    assert f["candidates"][0]["true_from"] == f["true_from"]


def test_ember_dates_are_served_with_the_headers_the_corpus_gives(sc):
    """S3-TF-1 S3-TF-2 (the mock serves `Effective:` as written, also an invalid one: the service must read it)"""
    texts = {}
    for c in successful(sc.windows[EMB]):
        for s in c["served"]:
            if "Registrant:" in s["text"]:                    # a text with its header (a search snippet has none)
                texts.setdefault(s["url"], s["text"])
    for u in ("a", "c", "b"):
        assert f"https://ember-dates.test/{u}" in texts, f"no page text with its header was served for /{u}"
    assert "Effective: 2026-01-05" in texts["https://ember-dates.test/a"]
    assert "Effective: 2026-02-30" in texts["https://ember-dates.test/c"]
    assert "Effective:" not in texts["https://ember-dates.test/b"]


def test_old_pages_without_effective_take_the_date_of_published(sc):
    """S3-TF-2 (northwind: no Effective line anywhere; Published 2026-02-01T00:00:00Z)"""
    b = sc.bodies[NW]
    for name, f in six(b["fields"]).items():
        for c in f["candidates"]:
            assert c["true_from"] == "2026-02-01", (name, c)
        if f["value"] is not None:
            assert f["true_from"] == "2026-02-01" and dt(f["learned_at"]) == dt(b["researched_at"])
    for name in FIELDS:
        if b["fields"][name]["value"] is None:
            assert b["fields"][name] == UNKNOWN


# --------------------------------------------------------------------------- executives
def test_executives_is_a_seventh_field_after_the_six(sc):
    """S3-EX-1 S3-EX-3 (the fields of every dossier response hold executives after the six fields of §4; GET /dossiers
    is unchanged)"""
    for d in (EMB, PAX, MER, NW):
        b = sc.bodies[d]
        assert list(b["fields"]) == list(FIELDS) + ["executives", "investors"], list(b["fields"])   # stage 4: investors last
        assert set(b["fields"]["executives"]) >= {"value", "status", "true_from", "learned_at", "citations", "candidates"}
        check_shape(b)
    lst = ok_json(sc.w.ada.get("/dossiers", params={"limit": 200}))["dossiers"]
    assert lst and all(set(e) == {"dossier_id", "domain", "state", "legal_name", "researched_at", "spent_units"}
                       for e in lst)


def test_no_title_with_a_selected_person_is_unknown_with_null_value(sc):
    """S3-EX-3 S3-EX-9 (northwind and ember have no executive: value null, unknown, no citations, no candidates, both
    times null)"""
    for d in (NW, EMB):
        assert sc.bodies[d]["fields"]["executives"] == UNKNOWN, d


def test_executives_candidates_are_by_title_and_follow_the_rules(sc):
    """S3-EX-2 S3-EX-4 S3-EX-5 S3-EX-6 S3-EX-7 S3-EX-8 S3-EX-9 S3-EX-11 (meridian build 0: cfo contested between the
    company's page and an aggregator; candidates by title then rank; citations per member in order; true_from the
    latest of the members')"""
    b = sc.bodies[MER]
    check_build(b, sc.windows[MER], 0)
    e = b["fields"]["executives"]
    assert e["value"] == [{"title": "cfo", "name": "Ana Silva"}, {"title": "cto", "name": "Ben Okafor"}]
    assert e["status"] == "contested" and e["true_from"] == "2025-09-01"
    assert [(c["title"], c["value"], c["selected"]) for c in e["candidates"]] == [
        ("cfo", "Ana Silva", True), ("cfo", "Gus Hall", False), ("cto", "Ben Okafor", True)]
    assert [c["kind"] for c in e["candidates"]] == ["own", "aggregator", "own"]
    assert [c["url"].rsplit("/", 1)[1] for c in e["citations"]] == ["exec", "exec"]    # one per member
    assert e["citations"][0]["excerpt"] and "Ana Silva" in e["citations"][0]["excerpt"]
    assert "Ben Okafor" in e["citations"][1]["excerpt"]
    assert dt(e["learned_at"]) == dt(b["researched_at"])
    for c in e["candidates"]:
        assert set(c) >= {"title", "value", "url", "excerpt", "provider", "kind", "published_at", "retrieved_at",
                          "selected", "true_from", "learned_at"}
    # the six fields: a CFO sentence is not a CEO sentence
    assert b["fields"]["ceo"]["value"] == "Dana Ruiz" and b["fields"]["ceo"]["status"] == "contested"


def test_research_still_asks_for_the_six_fields_only(sc):
    """S3-EX-2 (a research run asks for the six fields of §4; no research claim is a candidate of executives)"""
    runs = [c for c in successful(sc.windows[MER]) if c["method"] == "research"]
    assert runs, "no research run"
    for c in runs:
        assert c["fields"] == sorted(FIELDS), c["fields"]
    for c in sc.bodies[MER]["fields"]["executives"]["candidates"]:
        assert c["url"].endswith("/exec") or c["url"].endswith("/meridian-ledger")


def test_executive_sentences_that_name_no_one_or_two_people_are_not_candidates(sc):
    """S3-EX-4 S3-EX-15 (paxton-quay: two names in one sentence, a former CFO, `will become`, a partner's CFO, `'s`
    after the company name; a fragment of a sentence may support a name: tolerated, never required)"""
    b = sc.bodies[PAX]
    check_build(b, sc.windows[PAX], 0)
    e = b["fields"]["executives"]
    got = {(c["title"], c["value"], c["url"].rsplit("/", 1)[1]) for c in e["candidates"]}
    assert ("cfo", "Iris Holt", "people") in got and ("cfo", "Walt Moss", "paxton-quay") in got
    assert ("coo", "Rhea Cho", "people") in got and ("cto", "Yan Li Wu", "people") in got
    assert not any(v in ("Walt Moss", "Sara Lund", "Tom Wells") and u == "people" for _, v, u in got), got
    assert e["status"] == "contested"                                 # the cfo candidates carry two names
    names = {x["title"]: x["name"] for x in e["value"]}
    assert names["coo"] == "Rhea Cho" and names["cto"] == "Yan Li Wu" and "cfo" in names
    assert [x["title"] for x in e["value"]] == ["cfo", "coo", "cto"]
    # statement phrases: a person who is only CEO is not an executive title of this field
    assert all(c["title"] in ("cfo", "coo", "cto") for c in e["candidates"])


def test_a_dossier_with_only_a_contested_executive_has_no_contested_six_fields(sc):
    """S3-EX-14 (contested is judged on the six fields: paxton's executives are contested, its six fields are not)"""
    b = sc.bodies[PAX]
    assert b["fields"]["executives"]["status"] == "contested"
    assert all(f["status"] != "contested" for f in six(b["fields"]).values())


def test_titles_have_the_phrases_of_the_specification():
    """S3-EX-4 (offline: the oracle's phrases for cfo/coo/cto are the table of stage-3.md; ceo's value format)"""
    assert o.PHRASES["cfo"] == ["chief financial officer", "CFO"]
    assert o.PHRASES["coo"] == ["chief operating officer", "COO"]
    assert o.PHRASES["cto"] == ["chief technology officer", "CTO"]
    d = "acme-robotics.test"
    assert o.supported_values("Ana Silva is the chief financial officer of Acme Robotics.", "cfo", d) == {"Ana Silva"}
    assert o.supported_values("Acme Robotics CTO: Ben Okafor.", "cto", d) == {"Ben Okafor"}
    assert o.supported_values("Acme Robotics CTO: Ben Okafor.", "cfo", d) == set()
    assert o.supported_values("Acme Robotics COO Mary Anne Cole.", "coo", d) == {"Mary Anne Cole"}
