"""Stage 4: the `investors` field (vantage-mill.test, one build; gen_corpus.py stage-4 section). IDs (S4-*) in docstrings
refer to ../LEDGER.md. Literal expectations are derived by hand from stage-4.md Investors and the corpus."""
import pytest

import oracle as o
import s3model as s3
from conftest import BASE, MOCK, UNKNOWN, ALL_FIELDS, check_build, ok_json
from s3util import values
from s3util import dt
from s4util import V, single_build

ABOUT, REG = "https://vantage-mill.test/about", "https://registry-open.test/vantage-mill"
WIRE, COPY = "https://wirecast-daily.test/vantage-round", "https://localpress.test/vantage-round"
TICK, DEAL = "https://tickerpost.test/vantage-backers", "https://dealwire.test/vantage-mill"
LOOK, MIRROR = "https://vantage-mill-co.test/about", "https://scrape-mirror.test/vm"
MEMBERS = ["Bluebird Capital", "Cedar Capital", "Index Ventures", "Northwind Ventures", "Orion Equity Partners"]
BY_URL = {ABOUT: {"Bluebird Capital", "Northwind Ventures"}, REG: {"Orion Equity Partners"},
          WIRE: {"General Atlantic"}, COPY: {"General Atlantic"},
          TICK: {"Sequoia Capital", "Index Ventures", "Accel Partners", "Cedar Capital"},
          DEAL: {"Index Ventures", "Åkerlund Capital"}, LOOK: {"Cedar Capital"}, MIRROR: {"Orion Equity Partners"}}
ORDER = [(REG, "Orion Equity Partners"), (ABOUT, "Bluebird Capital"), (ABOUT, "Northwind Ventures"),
         (COPY, "General Atlantic"), (TICK, "Accel Partners"), (TICK, "Cedar Capital"), (TICK, "Index Ventures"),
         (TICK, "Sequoia Capital"), (WIRE, "General Atlantic"), (MIRROR, "Orion Equity Partners"),
         (LOOK, "Cedar Capital"), (DEAL, "Index Ventures"), (DEAL, "Åkerlund Capital")]


@pytest.fixture(scope="module")
def vm():
    if not (BASE and MOCK):
        pytest.fail("BASE_URL and MOCK_URL are required")
    return single_build(V)


def inv(vm):
    return vm.body["fields"]["investors"]


def test_the_dossier_holds_eight_fields_with_investors_last(vm):
    """S4-INV-1 (the fields of every response that lists them: six, executives, investors)"""
    assert vm.body["state"] == "ready" and list(vm.body["fields"]) == list(ALL_FIELDS)
    assert ALL_FIELDS[-2:] == ("executives", "investors")
    check_build(vm.body, vm.calls)
    assert vm.body["fields"]["executives"] == UNKNOWN


def test_candidates_are_the_investor_names_each_page_supports(vm):
    """S4-INV-2 S4-INV-3 S4-INV-4 (names of the runs that end in Ventures, Capital, Partners, Fund, Investments, Holdings or
    Equity; `led by`/`backed by` with an amount names its run; not `led by Dana Ruiz`, `Alpha Investors Fund` (the phrase
    `investors` is taken out), `Vantage Mill Ventures` (the company's name is taken out), `the Gates Foundation`
    (no amount rule match: lower case word), nor a negated sentence; the name as the excerpt writes it)"""
    f = inv(vm)
    by = {}
    for c in f["candidates"]:
        by.setdefault(c["url"], set()).add(c["value"])
    assert by == BY_URL, {u: (by.get(u), BY_URL[u]) for u in BY_URL if by.get(u) != BY_URL[u]}
    names = {c["value"] for c in f["candidates"]}
    for no in ("Dana Ruiz", "Alpha Investors Fund", "Alpha", "Fund", "Gates Foundation", "Vantage Mill Ventures",
               "Ventures", "Zeta Capital", "Capital", "Union Square Hospitality Group"):
        assert no not in names, no
    for c in f["candidates"]:
        assert "title" not in c and isinstance(c["value"], str)
        assert o.supports(c["excerpt"], "investors", c["value"], V), (c["value"], c["excerpt"])


def test_members_are_own_or_filing_names_or_names_with_two_origins(vm):
    """S4-INV-5 S4-INV-6 S4-INV-7 (value = the members' names sorted by code point: own page, filing, two origins; General
    Atlantic is on a wire page and its syndicated copy: one origin; `Åkerlund Capital` and the others have one news or
    aggregator origin; a lookalike gives the company's own domain as a second origin without being `own`)"""
    f = inv(vm)
    assert f["value"] == MEMBERS and f["status"] == "known"
    assert [c["selected"] for c in f["candidates"]] == [c["value"] in MEMBERS for c in f["candidates"]]
    assert sorted({c["value"] for c in f["candidates"]} - set(MEMBERS)) == [
        "General Atlantic", "Sequoia Capital", "Accel Partners", "Åkerlund Capital"][:0] + sorted(
        ["Accel Partners", "General Atlantic", "Sequoia Capital", "Åkerlund Capital"])
    look = [c for c in f["candidates"] if c["url"] == LOOK][0]
    assert look["kind"] == "aggregator" and look["origin"] == "vantage-mill.test"
    assert f["candidates"][0]["value"] == "Orion Equity Partners" and f["candidates"][0]["kind"] == "filing"


def test_candidates_are_listed_in_the_order_of_the_selection_rule(vm):
    """S4-INV-8 (authority, recency, URL, provider, value: the registry filing, the own page, the news pages, then the
    aggregators; in each page the names by value)"""
    got = [(c["url"], c["value"]) for c in inv(vm)["candidates"]]
    assert got == ORDER, got


def test_citations_are_those_of_every_candidate_of_each_member_in_value_order(vm):
    """S4-INV-9 (for each member in the order of the value: the url, excerpt and provider of each of its candidates, rank order)"""
    f = inv(vm)
    want = [(ABOUT, "Bluebird Capital"), (TICK, "Cedar Capital"), (LOOK, "Cedar Capital"), (TICK, "Index Ventures"),
            (DEAL, "Index Ventures"), (ABOUT, "Northwind Ventures"), (REG, "Orion Equity Partners"),
            (MIRROR, "Orion Equity Partners")]
    assert [c["url"] for c in f["citations"]] == [u for u, _ in want]
    for c, (u, n) in zip(f["citations"], want):
        assert set(c) == {"url", "excerpt", "provider"} and o.supports(c["excerpt"], "investors", n, V), (u, n, c)


def test_true_from_of_a_member_is_the_earliest_known_and_the_fields_is_the_latest(vm):
    """S4-INV-10 (members' true_from: Bluebird and Northwind 2022-01-01, Orion 2023-03-01, Cedar and Index 2025-01-01; the
    field's the latest; learned_at the build's time)"""
    f = inv(vm)
    assert f["true_from"] == "2025-01-01"
    by = {}
    for c in f["candidates"]:
        by.setdefault(c["value"], []).append(c["true_from"])
    assert {n: min(t for t in by[n] if t) for n in MEMBERS} == {
        "Bluebird Capital": "2022-01-01", "Northwind Ventures": "2022-01-01", "Orion Equity Partners": "2023-03-01",
        "Cedar Capital": "2025-01-01", "Index Ventures": "2025-01-01"}
    assert dt(f["learned_at"]) == dt(vm.body["researched_at"])


def test_origins_and_corroboration_of_the_investors_field(vm):
    """S4-FK-8 S4-OR-8 (origins: of the candidates of all members, sorted; corroborated: every member has two or more
    origins: Bluebird, Northwind have one (their own page), so false; since null)"""
    f = inv(vm)
    assert f["origins"] == ["dealwire.test", "registry-open.test", "tickerpost.test", "vantage-mill.test"]
    assert f["corroborated"] is False and f["corroborated_since"] is None


@pytest.mark.parametrize("true_at,members", [
    ("2021-06-01", None),
    ("2022-06-01", ["Bluebird Capital", "Northwind Ventures"]),
    ("2023-06-01", ["Bluebird Capital", "Northwind Ventures", "Orion Equity Partners"]),
    ("2024-07-01", ["Bluebird Capital", "Northwind Ventures", "Orion Equity Partners"]),    # General Atlantic: one origin
    ("2025-03-01", ["Bluebird Capital", "Northwind Ventures", "Orion Equity Partners"]),    # Cedar, Index: one origin yet
    ("2025-07-01", ["Bluebird Capital", "Index Ventures", "Northwind Ventures", "Orion Equity Partners"]),
    ("2025-12-01", MEMBERS)])
def test_values_decides_membership_from_the_candidates_at_true_at(vm, true_at, members):
    """S4-INV-11 (`/values?true_at=`: pages hold from their Effective date; membership, value, true_from and citations of
    investors are decided from the candidates of the versions that hold on that date)"""
    j = ok_json(values(vm.w.ada, V, true_at))
    fl = j["fields"]["investors"]
    assert fl["value"] == members, (true_at, fl["value"])
    exp = s3.values_at([vm.model], vm.model.time, true_at)["investors"]
    assert fl["true_from"] == exp["true_from"] and [c["url"] for c in fl["citations"]] == exp["urls"], (true_at, fl, exp)
    if members is None:
        assert fl["true_from"] is None and fl["citations"] == []
