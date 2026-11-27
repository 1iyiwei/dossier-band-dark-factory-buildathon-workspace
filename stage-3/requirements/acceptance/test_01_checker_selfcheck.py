"""Self-check of the citation checker and corpus labels (no service). Ledger: AX-4 AX-5."""
import json
import pathlib

import pytest

import oracle as o
from conftest import check_citation, check_expect, EXPECT, served_index

HERE = pathlib.Path(__file__).parent


def served_for(domain, epoch=0):
    comp = json.loads((HERE / "corpus" / f"{domain}.json").read_text(encoding="utf-8"))
    calls = []
    for pg in comp["pages"]:
        if epoch in pg["epochs"]:
            head = f"Kind: {pg['kind']}\nRegistrant: {pg['lineage']['registrant']}\n"
            if pg["facts"]:
                head += "Facts: " + json.dumps(pg["facts"]) + "\n"
            calls.append({"provider": "nimble", "method": "search", "served": [
                {"url": pg["url"], "text": head + "\n" + pg["text"]}]})
    return calls


def test_checker_accepts_a_good_citation_and_rejects_bad_ones():            # AX-4
    idx = served_index(served_for("northwind-optics.test"))
    u = "https://northwind-optics.test/about"
    good = {"url": u, "provider": "nimble", "excerpt": "Northwind Optics was founded in 2009."}
    check_citation("northwind-optics.test", "founded_year", 2009, good, idx)
    with pytest.raises(AssertionError):      # wrong value
        check_citation("northwind-optics.test", "founded_year", 2010, good, idx)
    with pytest.raises(AssertionError):      # invented text
        check_citation("northwind-optics.test", "founded_year", 2009,
                       dict(good, excerpt="Northwind Optics was founded in 2009 by Ann."), idx)
    with pytest.raises(AssertionError):      # wrong provider
        check_citation("northwind-optics.test", "founded_year", 2009, dict(good, provider="tavily"), idx)
    with pytest.raises(AssertionError):      # unserved url
        check_citation("northwind-optics.test", "founded_year", 2009, dict(good, url=u + "x"), idx)
    with pytest.raises(AssertionError):      # not the right field
        check_citation("northwind-optics.test", "hq_city", 2009, good, idx)
    spaced = dict(good, excerpt="Northwind   Optics was founded\tin 2009.")
    check_citation("northwind-optics.test", "founded_year", 2009, spaced, idx)  # whitespace runs


def test_header_text_is_not_citable():                                      # AX-4
    idx = served_index(served_for("kestrel-freight.test"))
    c = {"url": "https://kestrel-freight.test/about", "provider": "nimble",
         "excerpt": 'Facts: {"hq_city": "Lisbon", "headcount_range": "51-200", "ceo": "Pedro Alves"}'}
    with pytest.raises(AssertionError):
        check_citation("kestrel-freight.test", "hq_city", "Lisbon", c, idx)


def test_fragment_of_a_hedged_sentence_is_rejected():                       # AX-4 SU-10
    idx = served_index(served_for("quillstone-bio.test"))
    c = {"url": "https://quillstone-bio.test/people", "provider": "nimble",
         "excerpt": "CEO Rosa Alvarez left Quillstone Bio in 2020."}
    assert o.supports(c["excerpt"], "ceo", "Rosa Alvarez", "quillstone-bio.test")  # literal reading
    with pytest.raises(AssertionError, match="hedged"):
        check_citation("quillstone-bio.test", "ceo", "Rosa Alvarez", c, idx)


@pytest.mark.parametrize("domain", sorted(EXPECT))
def test_labels_agree_with_the_oracle(domain):                              # AX-5
    import gen_corpus
    gen_corpus.check_labels()
