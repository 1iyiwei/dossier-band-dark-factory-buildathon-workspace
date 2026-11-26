"""Self-check of the test oracle against Appendix A (no service needed). Ledger: AX-1.
These pin the reading the acceptance tests use; a failure here is a bug in the tests."""
import pytest

import oracle as o

D = "acme-robotics.test"
V = lambda *a: set(a)  # noqa: E731

CASES = [
    # (excerpt, field, expected supported set)  -- A.2 examples
    ("Dana Ruiz has led Acme Robotics as chief executive since 2021.", "ceo", V("Dana Ruiz")),
    ("Acme Robotics CEO: Sam Ortiz.", "ceo", V("Sam Ortiz")),
    ("Acme Robotics was founded in 2014.", "founded_year", V(2014)),
    ("Acme Robotics employs about 120 people.", "headcount_range", V("51-200")),
    ("Acme Robotics is reportedly in talks to raise $40M.", "funding_total", V()),
    ("Acme Robotics opened a sales office in Porto.", "hq_city", V()),
    # funding amount forms
    ("Acme Robotics has raised $12M.", "funding_total", V(12000000)),
    ("Acme Robotics has raised 12 million dollars.", "funding_total", V(12000000)),
    ("Acme Robotics raised US$12 million.", "funding_total", V(12000000)),
    ("Acme Robotics raised USD 12 million.", "funding_total", V(12000000)),
    ("Acme Robotics raised $12,000,000.", "funding_total", V(12000000)),
    ("Acme Robotics raised $12.5 million.", "funding_total", V(12500000)),
    ("Acme Robotics raised $250k.", "funding_total", V(250000)),
    ("Acme Robotics raised $1.5bn.", "funding_total", V(1500000000)),
    ("Acme Robotics raised 12,000,000 US dollars.", "funding_total", V(12000000)),
    ("Acme Robotics raised €12 million.", "funding_total", V()),
    ("Acme Robotics raised 12 million euros.", "funding_total", V()),
    ("Acme Robotics raised $0.0000005 million.", "funding_total", V()),
    ("Acme Robotics raised $2M and $3M.", "funding_total", V()),
    ("Acme Robotics raised $12Mx.", "funding_total", V()),
    ("Acme Robotics raised A$12M.", "funding_total", V()),
    # headcount
    ("Acme Robotics has 1,200 employees.", "headcount_range", V("1001-5000")),
    ("Acme Robotics has 51-200 employees.", "headcount_range", V("51-200")),
    ("Acme Robotics has 100-300 employees.", "headcount_range", V()),
    ("Acme Robotics employs 120 people in 3 offices.", "headcount_range", V()),
    ("Acme Robotics employs 120 people as of 2025.", "headcount_range", V()),
    ("Acme Robotics employs 0 people.", "headcount_range", V()),
    ("Acme Robotics employs 12.5 people.", "headcount_range", V()),
    ("Acme Robotics employs 10 people.", "headcount_range", V("1-10")),
    ("Acme Robotics employs 20000 people.", "headcount_range", V("10001+")),
    ("Acme Robotics employs 120people.", "headcount_range", V()),
    ("Acme Robotics raised $5M and employs 120 people.", "headcount_range", V("51-200")),
    # founded
    ("Acme Robotics was founded in 2014 and raised $5M in 2019.", "founded_year", V()),
    ("Acme Robotics was founded in 1799.", "founded_year", V()),
    ("Acme Robotics was founded in 2100.", "founded_year", V()),
    ("Acme Robotics was founded in 1800.", "founded_year", V(1800)),
    ("Acme Robotics was founded in 20144.", "founded_year", V()),
    ("Acme Robotics was founded in 2014.5.", "founded_year", V()),
    ("Acme Robotics did not found anything.", "founded_year", V()),
    ("Acme Robotics was not founded in 2014.", "founded_year", V()),
    # hq
    ("Acme Robotics is headquartered in Lisbon, Portugal.", "hq_city", V("Lisbon")),
    ("Acme Robotics is headquartered in New York.", "hq_city", V("New York")),
    ("Acme Robotics is based in Zürich.", "hq_city", V("Zürich")),
    ("Acme Robotics is based in Aix-En-Provence.", "hq_city", V("Aix-En-Provence")),
    ("Acme Robotics is based in the Lisbon area.", "hq_city", V()),
    ("Acme Robotics is based in lisbon.", "hq_city", V()),
    ("Acme Robotics is based in Lisbon and has its head office in Porto.", "hq_city", V()),
    ("Acme Robotics is HEADQUARTERED IN Lisbon.", "hq_city", V("Lisbon")),
    # ceo
    ("Acme Robotics is led by chief executive officer Mary Anne Cole.", "ceo", V("Mary Anne Cole")),
    ("Dana Ruiz is the CEO of Acme Robotics and Sam Ortiz is its CFO.", "ceo", V()),
    ("Dana Ruiz and Sam Ortiz share the CEO role at Acme Robotics.", "ceo", V()),
    ("Acme Robotics CEO Dana.", "ceo", V()),
    ("Acme Robotics CEO Anna Maria Lucia Rossi.", "ceo", V()),
    ("Former CEO Dana Ruiz left Acme Robotics.", "ceo", V()),
    # legal name
    ("The legal name of Acme Robotics is Acme Robotics, Inc.", "legal_name", V("Acme Robotics, Inc.")),
    ("Acme Robotics Holdings Ltd is the registered company.", "legal_name", V("Acme Robotics Holdings Ltd")),
    ("Acme Robotics GmbH is the legal entity.", "legal_name", V("Acme Robotics GmbH")),
    ("Acme Robotics Pty Ltd is the legal entity.", "legal_name", V("Acme Robotics Pty Ltd")),
    ("Acme Robotics is the legal name.", "legal_name", V()),
    ("Acme Robotics Group is the legal name.", "legal_name", V()),
    ("The legal name of acme-robotics.test is Acme Robotics S.A.", "legal_name", V("Acme Robotics S.A.")),
    # sentences
    ("Acme Robotics, Inc. was founded in 2014.", "founded_year", V(2014)),
    ("Acme Robotics was founded in 2014. It employs 120 people.", "founded_year", V()),
    ("It employs 120 people.", "headcount_range", V()),
    # name / domain matching
    ("Acme was founded in 2014.", "founded_year", V()),
    ("Acme Roboticsx was founded in 2014.", "founded_year", V()),
    ("acme-robotics.test was founded in 2014.", "founded_year", V(2014)),
    ("ACME ROBOTICS was founded in 2014.", "founded_year", V(2014)),
    ("Visit www.acme-robotics.test: founded in 2014.", "founded_year", V(2014)),
    ("Acme Robotics\tCorp  was   founded in 2014.", "founded_year", V(2014)),
    # negation words
    ("Acme Robotics could have been founded in 2014.", "founded_year", V()),
    ("Acme Robotics, formerly known as X, was founded in 2014.", "founded_year", V()),
    ("Acme Robotics was founded in 2014 (note this).", "founded_year", V(2014)),
]


@pytest.mark.parametrize("excerpt,field,expected", CASES)
def test_oracle_cases(excerpt, field, expected):          # AX-1
    assert o.supported_values(excerpt, field, D) == expected


def test_sentence_splitter():                           # AX-2
    s = o.sentences
    assert s("A b. C d.") == ["A b.", "C d."]
    assert s("Acme, Inc. was founded. Next one!") == ["Acme, Inc. was founded.", "Next one!"]
    assert s('He said "yes." Then left.') == ['He said "yes."', "Then left."]
    assert s("one\ntwo. three\n\nfour") == ["one", "two.", "three", "four"]
    assert s("Version 1.5 is out. Done") == ["Version 1.5 is out.", "Done"]
    assert s("Foo Ltd. Bar") == ["Foo Ltd.", "Bar"]          # Ltd has no dot of its own
    assert s("Foo S.A. Bar. Baz") == ["Foo S.A. Bar.", "Baz"]
    assert not o.is_single_sentence("Acme was founded in 2014. It is big.")
    assert o.is_single_sentence("Acme Robotics, Inc. was founded in 2014.")


def test_header_vs_prose():                             # AX-3
    t = "Kind: news\nFacts: {\"ceo\": \"X Y\"}\n\nAcme Robotics was founded in 2014."
    assert o.prose_of(t) == "Acme Robotics was founded in 2014."
    assert o.prose_of("Acme Robotics was founded in 2014.\nKind: news") .startswith("Acme")
    assert o.prose_of("CEO: Sam Ortiz\n\nx") == "CEO: Sam Ortiz\n\nx"
