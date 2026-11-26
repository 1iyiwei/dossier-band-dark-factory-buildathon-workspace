"""Generates corpus/*.json (mock-web format) and expectations.json for the acceptance tests.

Run: python3 gen_corpus.py   (it also checks every expectation label against oracle.py).
Labels per field: ["K", [values]]  must be known, value one of the listed;
                  ["U"]            no excerpt can support any value: must be unknown;
                  ["F", [values]]  sentence-level unsupported but a fragment supports: either.
"""
import json
import pathlib

import oracle as o

OUT = pathlib.Path(__file__).parent / "corpus"
PUB = "2026-02-01T00:00:00Z"


def page(domain, path, text, *, kind="own", epochs=(0,), searchable=True, facts=None,
         title=None, host=None, canonical=None, first=None):
    host = host or domain
    return {"url": f"https://{host}/{path}", "kind": kind, "epochs": list(epochs),
            "searchable": searchable, "published_at": PUB, "true_from": None,
            "title": title or f"{path} - {host}", "text": "\n".join(text),
            "facts": facts or {},
            "lineage": {"canonical": canonical, "first_published_by": first, "registrant": host}}


C = {}   # domain -> dict(names, pages, research)
E = {}   # domain -> epoch -> field -> label


def company(domain, name, pages, research=None):
    C[domain] = {"domain": domain, "names": [name], "pages": pages, "research": research or {}}


# ---- A: northwind-optics.test: clean, two epochs
d = "northwind-optics.test"
about = ["Northwind Optics designs lenses for medical imaging devices.",
         "Northwind Optics is headquartered in Lisbon.",
         "Northwind Optics was founded in 2009."]
company(d, "Northwind Optics", [
    page(d, "about", about, epochs=(0, 1), title="About Northwind Optics"),
    page("mirror-archive.test", "northwind-optics/about", about, kind="aggregator",
         epochs=(0, 1), host="mirror-archive.test", first=d, title="Northwind Optics (mirror)"),
    page(d, "legal", ["The legal name of Northwind Optics is Northwind Optics, Inc."], kind="filing",
         title="Registration"),
    page(d, "leadership", ["Mara Voss has led Northwind Optics as chief executive since 2021."],
         title="Leadership"),
    page(d, "leadership", ["Tomas Klein has led Northwind Optics as chief executive since 2026.",
                           "Mara Voss is the former CEO of Northwind Optics."],
         epochs=(1,), title="Leadership"),
    page(d, "team", ["Northwind Optics employs about 120 people across three offices."],
         title="Team"),
    page(d, "team", ["Northwind Optics employs roughly 240 people across three offices."],
         epochs=(1,), title="Team"),
    page("wirecast-daily.test", "northwind-raises",
         ["Northwind Optics has raised $18M in total funding.",
          "Northwind Optics opened an office in Porto."], kind="news",
         host="wirecast-daily.test", title="Northwind raises"),
    page("wirecast-daily.test", "northwind-raises",
         ["Northwind Optics has raised $25M in total funding.",
          "Northwind Optics opened an office in Porto."], kind="news", epochs=(1,),
         host="wirecast-daily.test", title="Northwind raises"),
], {"nimble": {"0": [{"field": "ceo", "value": "Mara Voss",
                      "url": f"https://{d}/leadership",
                      "excerpt": "Mara Voss has led Northwind Optics as chief executive since 2021."}],
               "1": [{"field": "ceo", "value": "Tomas Klein",
                      "url": f"https://{d}/leadership",
                      "excerpt": "Tomas Klein has led Northwind Optics as chief executive since 2026."}]}})
E[d] = {
    "0": {"legal_name": ["K", ["Northwind Optics, Inc."]], "hq_city": ["K", ["Lisbon"]],
          "ceo": ["K", ["Mara Voss"]], "founded_year": ["K", [2009]],
          "headcount_range": ["K", ["51-200"]], "funding_total": ["K", [18000000]]},
    "1": {"legal_name": ["U"], "hq_city": ["K", ["Lisbon"]], "ceo": ["K", ["Tomas Klein"]],
          "founded_year": ["K", [2009]], "headcount_range": ["K", ["201-500"]],
          "funding_total": ["K", [25000000]]}}

# ---- B: kestrel-freight.test: research-only facts, Facts header trap, bad research claims
d = "kestrel-freight.test"
lead = [f"Ines Duarte is the CEO of Kestrel Freight.",
        "Kestrel Freight has raised $12M in funding to date.",
        "Kestrel Freight might employ 300 people.",
        "Kestrel Freight opened a depot in Porto."]
company(d, "Kestrel Freight", [
    page(d, "about", ["Kestrel Freight was established in 1998.",
                      "Kestrel Freight moves containers across Iberia."],
         facts={"hq_city": "Lisbon", "headcount_range": "51-200", "ceo": "Pedro Alves"}),
    page(d, "legal", ["The legal entity behind Kestrel Freight is Kestrel Freight GmbH."],
         kind="filing"),
    page(d, "leadership", lead, searchable=False),
], {"nimble": {"0": [
    {"field": "ceo", "value": "Ines Duarte", "url": f"https://{d}/leadership", "excerpt": lead[0]},
    {"field": "funding_total", "value": 12000000, "url": f"https://{d}/leadership",
     "excerpt": lead[1]},
    {"field": "headcount_range", "value": "201-500", "url": f"https://{d}/leadership",
     "excerpt": lead[2]},
    {"field": "hq_city", "value": "Porto", "url": f"https://{d}/leadership", "excerpt": lead[3]},
]}})
E[d] = {"0": {"legal_name": ["K", ["Kestrel Freight GmbH"]], "hq_city": ["U"],
              "ceo": ["K", ["Ines Duarte"]], "founded_year": ["K", [1998]],
              "headcount_range": ["U"], "funding_total": ["K", [12000000]]}}

# ---- C: quillstone-bio.test: hedges, negation, other currency, conflicts inside a sentence
d = "quillstone-bio.test"
company(d, "Quillstone Bio", [
    page(d, "about", ["Quillstone Bio develops enzyme therapies for rare diseases.",
                      "Quillstone Bio is headquartered in Zürich.",
                      "Quillstone Bio is not headquartered in Geneva.",
                      "Quillstone Bio is reportedly based in Basel.",
                      "Quillstone Bio is registered as Quillstone Biosciences Ltd.",
                      "Quillstone Bio was formerly registered as Quillstone Bio Ltd."]),
    page(d, "people", ["Former CEO Rosa Alvarez left Quillstone Bio in 2020.",
                       "Wen Zhao has been chief executive of Quillstone Bio since 2022."]),
    page(d, "funding", ["Quillstone Bio was founded in 2011 and raised $4M in 2013.",
                        "Quillstone Bio is in talks to raise $40M.",
                        "Quillstone Bio raised €30 million in 2019.",
                        "Quillstone Bio plans to raise $60 million next year."], kind="news"),
    page(d, "staff", ["Quillstone Bio employs 85 people in 3 labs."]),
])
E[d] = {"0": {"legal_name": ["F", ["Quillstone Bio Ltd"]], "hq_city": ["K", ["Zürich"]],
              "ceo": ["K", ["Wen Zhao"]], "founded_year": ["F", [2011]],
              "headcount_range": ["F", ["51-200"]], "funding_total": ["K", [4000000]]}}

# ---- D: tidewell-pharma.test: formats (unicode place, three-word CEO, 1,200, decimal million)
d = "tidewell-pharma.test"
company(d, "Tidewell Pharma", [
    page(d, "about", ["Tidewell Pharma plc is the registered company behind the Tidewell brand.",
                      "Tidewell Pharma has its head office in San Sebastián, Spain.",
                      "Tidewell Pharma is led by chief executive officer Mary Anne Cole.",
                      "Tidewell Pharma was incorporated in 1987."]),
    page(d, "facts", ["Tidewell Pharma has 1,200 employees.",
                      "Tidewell Pharma has raised 12.5 million dollars in funding."], kind="news"),
])
E[d] = {"0": {"legal_name": ["K", ["Tidewell Pharma plc"]], "hq_city": ["K", ["San Sebastián"]],
              "ceo": ["K", ["Mary Anne Cole"]], "founded_year": ["K", [1987]],
              "headcount_range": ["K", ["1001-5000"]], "funding_total": ["K", [12500000]]}}

# ---- E: orchard-lane-foods.test: hyphenated city, range, sub-dollar amounts
d = "orchard-lane-foods.test"
company(d, "Orchard Lane Foods", [
    page(d, "about", ["Orchard Lane Foods Limited is the legal name.",
                      "Orchard Lane Foods is based in Stoke-on-Trent.",
                      "Orchard Lane Foods CEO: Anika Sørensen.",
                      "Orchard Lane Foods was established in 1999.",
                      "Orchard Lane Foods has a headcount of 51-200."]),
    page(d, "seed", ["Orchard Lane Foods raised $1.2345 million in seed funding.",
                     "Orchard Lane Foods raised $0.0000005 million in a micro round."],
         kind="news"),
])
E[d] = {"0": {"legal_name": ["K", ["Orchard Lane Foods Limited"]], "hq_city": ["K", ["Stoke"]],
              "ceo": ["K", ["Anika Sørensen"]], "founded_year": ["K", [1999]],
              "headcount_range": ["K", ["51-200"]], "funding_total": ["K", [1234500]]}}

# ---- F: bluefin-marine.test: aggregator restating / contradicting, region for a city
d = "bluefin-marine.test"
company(d, "Bluefin Marine", [
    page(d, "about", ["Bluefin Marine was founded in 2005.",
                      "Bluefin Marine employs about 45 people.",
                      "Bluefin Marine raised $3M in a seed round.",
                      "Bluefin Marine is headquartered in Scandinavia.",
                      "Bluefin Marine's chief executive is Lena Okafor.",
                      "The registered name of Bluefin Marine is Bluefin Marine Holdings Ltd."]),
    page("bizlistings-hub.test", "bluefin-marine",
         ["Bluefin Marine was founded in 2008, according to our listings.",
          "Bluefin Marine has approximately 4,500 employees.",
          "Bluefin Marine has raised $21M in total.",
          "Bluefin Marine CEO Lena Okafor and CFO Jin Park joined in 2019."],
         kind="aggregator", host="bizlistings-hub.test", first=d),
])
E[d] = {"0": {"legal_name": ["K", ["Bluefin Marine Holdings Ltd"]],
              "hq_city": ["K", ["Scandinavia"]], "ceo": ["K", ["Lena Okafor"]],
              "founded_year": ["K", [2005, 2008]],
              "headcount_range": ["K", ["11-50", "1001-5000"]],
              "funding_total": ["K", [3000000, 21000000]]}}

# ---- G: no-trace.test: nothing about it exists; a look-alike company is the decoy
d = "notrace-systems.test"
company(d, "Notrace Systems", [
    page(d, "about", ["Notrace Systems was founded in 1999.",
                      "Notrace Systems is headquartered in Berlin.",
                      "Notrace Systems employs 30 people."])])
E["no-trace.test"] = {"0": {f: ["U"] for f in o.FIELDS}}

# ---- H: harbor-signal.test: sentence splitting (legal-form period, two sentences, line break)
d = "harbor-signal.test"
company(d, "Harbor Signal", [
    page(d, "about", ["Harbor Signal, Inc. was founded in 2012. It employs 60 people.",
                      "Harbor Signal is based in Oslo, Norway, and builds buoys.",
                      "Harbor Signal's CEO is Priya",
                      "Nair.",
                      "Harbor Signal raised $2M in seed and $5M in Series A."])])
E[d] = {"0": {"legal_name": ["U"], "hq_city": ["K", ["Oslo"]], "ceo": ["F", ["Priya Nair"]],
              "founded_year": ["K", [2012]], "headcount_range": ["U"],
              "funding_total": ["F", [2000000]]}}


def check_labels():
    for dom, epochs in E.items():
        for ep, labels in epochs.items():
            comp = C.get(dom)
            texts = []
            if comp:
                for pg in comp["pages"]:
                    if int(ep) in pg["epochs"] and pg["searchable"]:
                        texts.append(pg["text"])
                for r in comp["research"].get("nimble", {}).get(ep, []):
                    texts.append(r["excerpt"])
                for pg in comp["pages"]:      # research citations of unsearchable pages
                    pass
            for f, lab in labels.items():
                sent = o.sentence_values(texts, f, dom)
                span = o.evidence_values(texts, f, dom)
                if lab[0] == "K":
                    assert sent and sent <= set(lab[1]) <= span, (dom, ep, f, lab, sent, span)
                elif lab[0] == "U":
                    assert not span, (dom, ep, f, span)
                else:
                    assert not sent, (dom, ep, f, sent, span)


if __name__ == "__main__":
    check_labels()
    OUT.mkdir(exist_ok=True)
    for f in OUT.glob("*.json"):
        f.unlink()
    for dom, comp in C.items():
        (OUT / f"{dom}.json").write_text(json.dumps(comp, ensure_ascii=False, indent=1) + "\n",
                                         encoding="utf-8")
    (OUT / "traits.json").write_text(json.dumps(
        {"seed": 7, "providers": {"nimble": {"noise": 0.0, "rate_limit": 0.0},
                                  "tavily": {"noise": 0.0, "rate_limit": 0.0}}}) + "\n")
    (pathlib.Path(__file__).parent / "expectations.json").write_text(
        json.dumps(E, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("ok", len(C), "companies")
