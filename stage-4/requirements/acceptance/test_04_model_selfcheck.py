"""Offline checks (no service) of the stage-4 model (oracle investors, lineage.py, s3model corroboration and investors
typing) against stage-4.md read by hand, and of the stage-4 corpus design. IDs (AX-*) in ../LEDGER.md."""
from datetime import datetime

import oracle as o
import lineage as lin
import s2model as m
import s3model as s3
from conftest import CORPUS_S2

D = lambda s: datetime.fromisoformat(s)
VM = "vantage-mill.test"


def test_investor_names_by_appendix_a_extension():
    """AX-10 (stage-4.md Investors: phrases taken out, runs of capitalised words, the last-word list, the amount rule)"""
    n = lambda t: sorted(o.investor_names(t, VM))
    assert n("Vantage Mill raised $40M in a round led by General Atlantic.") == ["General Atlantic"]
    assert n("Vantage Mill is led by Dana Ruiz.") == []
    assert n("Vantage Mill is backed by General Atlantic.") == []                       # no amount, no last word
    assert n("Northwind Ventures and Bluebird Capital are investors in Vantage Mill.") == ["Bluebird Capital", "Northwind Ventures"]
    assert n("Vantage Mill is backed by Alpha Investors Fund.") == []                   # `Investors` is a phrase: taken out
    assert n("Vantage Mill Ventures participated in a round.") == []                    # the company's name is taken out
    assert n("Vantage Mill is not backed by Orion Equity Partners.") == []              # negating phrase
    assert n("Vantage Mill raised $9M in a round led by the Gates Foundation.") == []
    assert n("Vantage Mill raised $20M in a round led by Union Square Hospitality Group.") == ["Union Square Hospitality Group"]
    assert n("Vantage Mill raised $9M led by Alpha Beta Ventures, with participation from Delta Ventures.") == ["Alpha Beta Ventures", "Delta Ventures"]
    assert n("vantage-mill.test is backed by Åkerlund Capital and Zürich Ventures.") == ["Zürich Ventures", "Åkerlund Capital"]
    assert n("Vantage Mill is backed by Blue-Sky Capital.") == ["Sky Capital"]           # words joined by single spaces only
    assert n("Kestrel Peak Capital Fund is an investor in Vantage Mill.") == ["Kestrel Peak Capital Fund"]
    assert n("Sequoia Capital invested in Acme Corp.") == []                            # does not name the company


def test_origin_rules():
    """AX-10 (the four rules, the three-Canonical limit, cycles, unserved originals; stage-4.md Origins)"""
    P = lambda u, **l: {"url": u, "kind": "aggregator", "lineage": l}
    pg = {u: P(u, **l) for u, l in {
        "https://a.test/x": dict(canonical="https://b.test/x", registrant="a.test"),
        "https://b.test/x": dict(canonical="https://c.test/x", registrant="b.test"),
        "https://c.test/x": dict(canonical="https://d.test/x", registrant="c.test"),
        "https://d.test/x": dict(canonical="https://e.test/x", registrant="d.test"),
        "https://e.test/x": dict(canonical=None, registrant="reg-e.test")}.items()}
    o_ = lambda u: lin.origin(pg[u], u, "co.test", pg.get)
    assert o_("https://a.test/x") == "e.test" and o_("https://b.test/x") == "reg-e.test" and o_("https://e.test/x") == "reg-e.test"
    lk = P("https://lookalike.test/x", registrant="elsewhere.test")
    lk["kind"] = "own"
    assert lin.origin(lk, lk["url"], "co.test", pg.get) == "co.test" and m.kind_of(lk, lk["url"], "co.test") == "aggregator"
    assert lin.origin(dict(lk, lineage={"registrant": "x.test", "first_published_by": "WWW.Wire.TEST."}), lk["url"], "co.test", pg.get) == "wire.test"
    bad = P("https://h.test/x", registrant="https://h.test/x")
    assert m.registrant_of(bad, bad["url"]) == "h.test"


def test_corpus_designs_read_as_intended():
    """AX-10 (lumen-forge, hollow-reach, kindred-mark, keen-lantern, vantage-mill, prism-harbor: origins and members)"""
    def origins(d, e=0):
        return {u.split("//")[1]: v for u, v in s3.page_origins(d, e, CORPUS_S2)[0].items()}
    assert origins("lumen-forge.test")["scrapehub.test/lf"] == "lumen-forge.test"
    assert origins("lumen-forge.test")["localpress.test/lumen-raise"] == "wirecast-daily.test"
    assert origins("hollow-reach.test")["chain-a.test/hr"] == "orig-registry.test"
    assert origins("hollow-reach.test")["deep-a.test/hr"] == "deep-e.test"
    assert origins("hollow-reach.test")["wwwcanon.test/hr"] == "mixed-case.test"
    assert origins("kindred-mark.test")["registry-one.test/km"] == "registry-one.test"
    b = s3.build_from_epoch(VM, 0, D("2026-03-01T09:00:00+00:00"), CORPUS_S2)
    assert s3.inv_of(b.candidates()["investors"])["value"] == [
        "Bluebird Capital", "Cedar Capital", "Index Ventures", "Northwind Ventures", "Orion Equity Partners"]
    for d in ("lumen-forge.test", "hollow-reach.test", "kindred-mark.test", "keen-lantern.test", "vantage-mill.test"):
        res, _, _ = s3.expected_all(d, 0, CORPUS_S2)
        assert all(not v["may"] for k, v in res.items() if k != "investors"), d     # investors: fragments may name a sub-run
        assert sum(1 for p in CORPUS_S2[d]["pages"] if p.get("searchable", True) and 0 in p["epochs"]) <= 8


def test_investors_typing_by_name():
    """AX-10 (a name added with true_from on or before the earlier value's: correction; later: change; a name that left: change)"""
    mem = lambda *t: [{"name": a, "true_from": f} for a, f in t]
    c = s3.classify_inv
    assert c((mem(("A", "2025-01-01")), "2025-01-01"), (mem(("A", "2025-01-01"), ("B", "2024-01-01")), "2025-01-01")) == "correction"
    assert c((mem(("A", "2025-01-01")), "2025-01-01"), (mem(("A", "2025-01-01"), ("B", "2025-02-01")), "2025-02-01")) == "change"
    assert c((mem(("A", "2025-01-01"), ("B", "2024-01-01")), "2025-01-01"), (mem(("A", "2025-01-01")), "2025-01-01")) == "change"
    assert c((mem(("A", None)), None), (mem(("A", None), ("B", "2020-01-01")), None)) == "change"
    assert c((mem(("A", "2025-01-01")), "2025-01-01"), (mem(("A", "2025-01-01"), ("B", None)), None)) == "change"


def test_standing_origins_across_builds():
    """AX-10 (corroborated_since: a second origin gathered once stands; a new selected value starts with none; a value that
    returns starts again; a member's run)"""
    def b(t, ceo, origins):
        cs = [{"value": ceo, "url": f"https://{o_}/x", "excerpt": "", "provider": "nimble", "kind": "own",
               "published_at": None, "true_from": None, "origin": o_} for o_ in origins]
        return s3.Build(D(t), {"u": (None, {"ceo": cs})})
    bs = [b("2026-01-01T00:00:00+00:00", "A B", ["x.test"]), b("2026-02-01T00:00:00+00:00", "A B", ["x.test", "y.test"]),
          b("2026-03-01T00:00:00+00:00", "A B", ["x.test"]), b("2026-04-01T00:00:00+00:00", "C D", ["x.test", "y.test"]),
          b("2026-05-01T00:00:00+00:00", "A B", ["x.test"])]
    r = [x["ceo"] for x in s3.corroboration(bs)]
    assert [x["since"] and x["since"].month for x in r] == [None, 2, 2, 4, None]
    assert [x["corroborated"] for x in r] == [False, True, False, True, False]
    assert [x["origins"] for x in r][2] == ["x.test"]
