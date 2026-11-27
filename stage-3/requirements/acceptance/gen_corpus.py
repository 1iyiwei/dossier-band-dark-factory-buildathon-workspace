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
         title=None, host=None, canonical=None, first=None, pub=PUB, static=None, url=None,
         true_from=None):
    """`pub`/`kind` are written verbatim into the Published/Kind header (None omits the line);
    `static` is what search/extract serve when it differs from what a browser shows (text).
    `true_from` is written verbatim into the Effective header (None omits the line)."""
    host = host or domain
    p = {"url": url or f"https://{host}/{path}", "kind": kind, "epochs": list(epochs),
         "searchable": searchable, "published_at": pub, "true_from": true_from,
         "title": title or f"{path} - {host}", "text": "\n".join(text),
         "facts": facts or {},
         "lineage": {"canonical": canonical, "first_published_by": first, "registrant": host}}
    if static is not None:
        p["static_text"] = "\n".join(static)
    return p


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

# ======================================================================= stage 2 companies
# Competing sources (selection rule), browser text vs served text, page kind and publication
# time defaults. Written from stage-2.md alone. Every sentence here is whole-sentence supported
# (no fragment-only candidates), so tests can assert exact candidate sets (s2model.py).

# ---- I: ashgrove-labs.test: every step of the selection rule
d = "ashgrove-labs.test"
company(d, "Ashgrove Labs", [
    page(d, "about", ["The legal name of Ashgrove Labs is Ashgrove Labs, Inc.",
                      "Ashgrove Labs was founded in 2011."],
         pub="2026-01-10T00:00:00Z", title="About Ashgrove Labs"),
    # same instant as /about written with another offset: a tie on recency; then the URL decides
    page(d, "registry", ["Ashgrove Labs was incorporated in 2010."], kind="filing",
         pub="2026-01-10T01:00:00+01:00", title="Registry entry"),
    page("bizdata-hub.test", "ashgrove-labs",
         ["The registered name of Ashgrove Labs is Ashgrove Labs Holdings Ltd.",
          "Ashgrove Labs is headquartered in Zagreb.",
          "Ashgrove Labs has its head office in Århus.",
          "Ashgrove Labs raised $9M in seed funding.",
          "Ashgrove Labs raised $10M in Series A funding."],
         kind="aggregator", host="bizdata-hub.test", pub="2026-02-20T00:00:00Z",
         title="Ashgrove Labs company data"),
    page("wirecast-daily.test", "ashgrove-profile", ["Ashgrove Labs CEO: Pat Lee."], kind="news",
         host="wirecast-daily.test", pub="2026-02-28T00:00:00Z", title="Ashgrove profile"),
    page(d, "team", ["Ashgrove Labs CEO: Sam Ortiz."], pub="2026-01-10T00:00:00Z", title="Team"),
    page(d, "careers", ["Ashgrove Labs employs about 120 people."], pub=None, title="Careers"),
    page(d, "jobs", ["Dana Ruiz has led Ashgrove Labs as chief executive since 2021.",
                     "Ashgrove Labs employs about 400 people."],
         pub="2020-01-01T00:00:00Z", title="Jobs"),
])

# ---- J: brightmoor-energy.test: browser text differs from served text; research cites pages
d = "brightmoor-energy.test"
company(d, "Brightmoor Energy", [
    page(d, "about", ["Brightmoor Energy is headquartered in Bristol.",
                      "Brightmoor Energy was founded in 2003.",
                      "Brightmoor Energy employs about 60 people."],
         static=["Brightmoor Energy is headquartered in Leeds.",
                 "Brightmoor Energy was founded in 1999."],
         pub="2026-02-01T00:00:00Z", title="About Brightmoor Energy"),
    page(d, "legal", ["The legal name of Brightmoor Energy is Brightmoor Energy Ltd."],
         kind="filing", pub="2026-02-01T00:00:00Z", title="Registration"),
    page(d, "leadership", ["Brightmoor Energy CEO: Ravi Menon."],
         static=["Brightmoor Energy CEO: Tom Hale."], searchable=False,
         pub="2026-02-01T00:00:00Z", title="Leadership"),
    page("wirecast-daily.test", "brightmoor-press",
         ["Brightmoor Energy is reportedly raising $7M in new funding.",
          "Brightmoor Energy has raised $5M in total funding to date."],
         static=["Press release archive."], kind="news", searchable=False,
         host="wirecast-daily.test", pub="2026-02-10T00:00:00Z", title="Brightmoor press"),
], {"nimble": {"0": [
    {"field": "ceo", "value": "Ravi Menon", "url": f"https://{d}/leadership",
     "excerpt": "Brightmoor Energy CEO: Ravi Menon."},
    {"field": "funding_total", "value": 7000000,
     "url": "https://wirecast-daily.test/brightmoor-press",
     "excerpt": "Brightmoor Energy is reportedly raising $7M in new funding."}]}})

# ---- K: cobalt-harbor.test: page kind and publication time, and their defaults (ceo only)
d = "cobalt-harbor.test"
def cobalt(url, ceo, kind, pub, title):
    return page(d, "", [f"Cobalt Harbor CEO: {ceo}."], kind=kind, pub=pub, url=url, title=title,
                host=url.split("/")[2])
company(d, "Cobalt Harbor", [
    cobalt("https://cobalt-harbor.test/about", "Ada Marsh", None, "2026-02-20T10:30:00+02:00", "About"),
    cobalt("https://www.cobalt-harbor.test/team", "Ben Cole", None, "2026-02-20T10:30:00.250Z", "Team"),
    cobalt("https://blog.cobalt-harbor.test/post", "Cy Dunn", None, "2026-02-20", "Blog post"),
    cobalt("https://wirecast-daily.test/cobalt", "Di Evans", "blog", "2026-02-30T00:00:00Z", "Cobalt notes"),
    cobalt("https://cobalt-harbor.test/legacy", "Eve Ford", "blog", "2026-02-20T10:30:00", "Legacy"),
    cobalt("https://newsy-corner.test/cobalt", "Gus Hill", "own", "2026-03-01T00:00:00Z", "Cobalt Harbor leadership"),
    cobalt("https://cobalt-harbor.test/press", "Hal Ivey", "news", "2026-03-02T00:00:00Z", "Press"),
])

# ---- L: driftwood-games.test: same value on several pages; URL code-point ties; duplicates
d = "driftwood-games.test"
P1 = "2026-01-15T00:00:00Z"
company(d, "Driftwood Games", [
    page(d, "About", ["Driftwood Games CEO: Zed Quinn.", "Driftwood Games was founded in 2012.",
                      "Driftwood Games was established in 2012."], pub=P1, title="About"),
    page(d, "about", ["Driftwood Games CEO: Amy Yu.", "Driftwood Games was founded in 2012."],
         pub=P1, title="about"),
    page(d, "about/", ["Driftwood Games was founded in 2012."], pub=P1, title="about slash"),
    page("wirecast-daily.test", "driftwood-wire", ["Driftwood Games has raised $12M in funding."],
         kind="news", host="wirecast-daily.test", pub="2026-02-02T00:00:00Z", title="Wire"),
    page("bizlistings-hub.test", "driftwood",
         ["Driftwood Games has raised 12 million dollars in funding."], kind="aggregator",
         host="bizlistings-hub.test", pub="2026-02-03T00:00:00Z", title="Listing"),
    page(d, "team", ["Driftwood Games employs about 120 people."], pub=P1, title="Team"),
    page(d, "careers", ["Driftwood Games has 90 employees."], pub=P1, title="Careers"),
])


# ======================================================================= stage 3 companies
# Change over time (stage-3.md). Written from stage-3.md alone. Every sentence is whole-sentence
# supported (no fragment-only candidates), so tests can compute exact expectations (s3model.py).
# Epochs are the "web changing between builds"; the tests set the clock and the epoch before each build.

# ---- M: meridian-ledger.test: the timeline company (five epochs; see test_s3_history.py)
d = "meridian-ledger.test"
N3 = "Meridian Ledger"
LEAD = f"https://{d}/leadership"


def lead(ep, text, tf, pub):
    return page(d, "leadership", [text], epochs=(ep,), searchable=False, true_from=tf, pub=pub,
                title="Leadership")


L0 = "Dana Ruiz has led Meridian Ledger as chief executive since 2021."
L1 = "Lee Park has led Meridian Ledger as chief executive since 2026."
L2 = "Sam Ortiz is the chief executive of Meridian Ledger."
L3 = "Meridian Ledger is led by its board."


def exec_page(ep, lines, tf, pub):
    return page(d, "exec", lines, epochs=(ep,), true_from=tf, pub=pub, title="Executive team")


CFO = "Ana Silva is the chief financial officer of Meridian Ledger."
COO = "Dee Hart is the chief operating officer of Meridian Ledger."
company(d, N3, [
    lead(0, L0, "2021-04-01", "2026-01-10T00:00:00Z"),
    lead(1, L1, "2026-03-20", "2026-03-25T00:00:00Z"),
    lead(2, L2, "2026-01-01", "2026-04-05T00:00:00Z"),
    lead(3, L3, "2026-05-01", "2026-05-02T00:00:00Z"),
    lead(4, L0, None, None),                                    # no Effective, no Published: true_from null
    # a stable fact: same value in every build; its Effective moves in epoch 2 (same value: no entry)
    page(d, "team", ["Meridian Ledger employs about 120 people."], epochs=(0, 1, 3, 4),
         true_from="2020-01-01", pub="2026-01-10T00:00:00Z", title="Team"),
    page(d, "team", ["Meridian Ledger employs about 120 people."], epochs=(2,),
         true_from="2019-06-01", pub="2026-04-05T00:00:00Z", title="Team"),
    # a field that is unknown until epoch 2
    page(d, "history", ["Meridian Ledger was founded in 2003."], epochs=(2, 3, 4),
         true_from="2026-04-01", pub="2026-04-05T00:00:00Z", title="History"),
    # executives
    exec_page(0, [CFO, "Meridian Ledger CTO: Ben Okafor."], "2025-09-01", "2026-01-10T00:00:00Z"),
    exec_page(1, [CFO, "Meridian Ledger CTO: Cho Min."], "2026-03-20", "2026-03-25T00:00:00Z"),
    exec_page(2, [CFO, "Meridian Ledger CTO: Cho Min.", COO], "2025-12-01", "2026-04-05T00:00:00Z"),
    exec_page(3, [CFO, "Meridian Ledger CTO: Eli Novak.", COO], "2025-10-01", "2026-05-02T00:00:00Z"),
    exec_page(4, [CFO, "Meridian Ledger CTO: Fay Quinn."], "2025-09-01", "2026-06-01T00:00:00Z"),
    # an aggregator that restates other sources; only served in epochs 0-2
    page("bizlistings-hub.test", "meridian-ledger",
         ["Meridian Ledger CEO: Pat Lee.", "Meridian Ledger CFO: Gus Hall."],
         kind="aggregator", epochs=(0, 1, 2), host="bizlistings-hub.test", true_from="2022-01-01",
         pub="2026-02-20T00:00:00Z", title="Meridian Ledger company data"),
], {"nimble": {"0": [{"field": "ceo", "value": "Dana Ruiz", "url": LEAD, "excerpt": L0}],
               "1": [{"field": "ceo", "value": "Lee Park", "url": LEAD, "excerpt": L1}],
               "2": [{"field": "ceo", "value": "Sam Ortiz", "url": LEAD, "excerpt": L2}],
               "3": [{"field": "ceo", "value": "Dana Ruiz", "url": LEAD, "excerpt": L3}],
               "4": [{"field": "ceo", "value": "Dana Ruiz", "url": LEAD, "excerpt": L0}]}})

# ---- P: paxton-quay.test: executive sentences that must not yield a person (tolerant check: fragments)
d = "paxton-quay.test"
company(d, "Paxton Quay", [
    page(d, "people", ["Paxton Quay CEO Dana Reyes and CFO Tom Wells joined in 2019.",
                       "Paxton Quay's chief financial officer is Iris Holt.",
                       "Former CFO Walt Moss left Paxton Quay in 2020.",
                       "Paxton Quay will become a public company and its COO Sara Lund will lead the listing.",
                       "Paxton Quay is advised by Brightline Partners, whose CFO is Tom Wells.",
                       "Paxton Quay COO: Rhea Cho.",
                       "Paxton Quay CTO: Yan Li Wu."], true_from="2025-02-01", pub="2026-02-01T00:00:00Z",
         title="People"),
    page("bizlistings-hub.test", "paxton-quay", ["Paxton Quay CFO: Walt Moss."], kind="aggregator",
         host="bizlistings-hub.test", true_from="2018-01-01", pub="2026-02-25T00:00:00Z",
         title="Paxton Quay company data"),
])

# ---- T: ember-dates.test: true_from of a page (Effective, Published, their defaults and invalid forms)
d = "ember-dates.test"
company(d, "Ember Dates", [
    page(d, "a", ["Ember Dates was founded in 2001."], true_from="2026-01-05", pub="2026-02-01T00:00:00Z"),
    page(d, "b", ["Ember Dates was founded in 2002."], pub="2026-02-10T23:30:00-05:00"),
    page(d, "c", ["Ember Dates was founded in 2003."], true_from="2026-02-30", pub="2026-03-01T00:30:00+02:00"),
    page(d, "d", ["Ember Dates was founded in 2004."], true_from="not a date", pub=None),
    page(d, "e", ["Ember Dates was founded in 2005."], pub="garbage"),
    page(d, "f", ["Ember Dates was founded in 2006."], true_from="2026-3-1", pub="2026-03-05T00:00:00Z"),
    page(d, "g", ["Ember Dates was founded in 2007."], true_from="2024-02-29", pub=None),
    page(d, "h", ["Ember Dates was founded in 2008."], true_from="2023-02-29", pub="2026-03-09T12:00:00Z"),
    page(d, "i", ["Ember Dates was founded in 2009."], true_from="2026-01-05T00:00:00Z",
         pub="2026-03-10T00:00:00Z"),
    page(d, "j", ["Ember Dates was founded in 2010."], true_from="2026-04-02", pub="2026-04-01T23:59:59.5-12:00"),
])

# ---- W: tally-wharf.test: sources that restate, republish and correct themselves
d = "tally-wharf.test"
company(d, "Tally Wharf", [
    page(d, "about", ["Tally Wharf CEO: Nia Cole."], epochs=(0,), true_from="2022-03-01",
         pub="2022-03-02T00:00:00Z", title="About"),
    page(d, "about", ["Tally Wharf CEO: Nia Cole."], epochs=(1,), true_from="2022-03-01",
         pub="2026-03-02T00:00:00Z", title="About (republished)"),
    page(d, "about", ["Tally Wharf CEO: Joe Hart."], epochs=(2,), true_from="2021-06-01",
         pub="2026-04-01T00:00:00Z", title="About"),
    page("wirecast-daily.test", "tally-raise", ["Tally Wharf has raised $12M in total funding."], kind="news",
         epochs=(0,), host="wirecast-daily.test", true_from="2024-01-01", pub="2024-01-02T00:00:00Z"),
    page("wirecast-daily.test", "tally-raise", ["Tally Wharf has raised $30M in total funding."], kind="news",
         epochs=(1, 2), host="wirecast-daily.test", true_from="2026-03-01", pub="2026-03-05T00:00:00Z"),
    # stale restatement: newer Published than the company's own page, older facts, lower authority
    page("bizlistings-hub.test", "tally-wharf", ["Tally Wharf CEO: Rob Dunn.",
                                                  "Tally Wharf raised $2M in its seed round."],
         kind="aggregator", epochs=(0, 1, 2), host="bizlistings-hub.test", pub="2026-03-10T00:00:00Z",
         title="Tally Wharf company data"),
])

# ---- F: fleet-*.test: six small companies whose CEO changes between epoch 0 and 1 (concurrency)
FLEET = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
PEOPLE = [("Ola Voss", "Ines Roca"), ("Mia Tran", "Noah Pike"), ("Tess Ward", "Ravi Shah"),
          ("Omar Bell", "Lena Fox"), ("Kai Lund", "Zoe Marsh"), ("Ed Dunn", "Uma Reed")]
for nm, (p0, p1) in zip(FLEET, PEOPLE):
    d = f"fleet-{nm}.test"
    Nm = f"Fleet {nm.capitalize()}"
    company(d, Nm, [
        page(d, "lead", [f"{Nm} CEO: {p0}."], epochs=(0,), true_from="2024-01-01", pub="2026-01-10T00:00:00Z"),
        page(d, "lead", [f"{Nm} CEO: {p1}."], epochs=(1,), true_from="2026-03-01", pub="2026-03-10T00:00:00Z"),
        page(d, "about", [f"{Nm} is headquartered in Lisbon."], epochs=(0, 1), true_from="2024-01-01",
             pub="2026-01-10T00:00:00Z"),
    ])

# ---- K: keystone-yards.test: what a stage-1/stage-2 service built and a stage-3 service imports
d = "keystone-yards.test"
KS = "Keystone Yards"
company(d, KS, [
    page(d, "about", [f"{KS} is headquartered in Gdansk.", f"{KS} was founded in 1995.",
                      f"The legal name of {KS} is {KS} GmbH."], epochs=(0,),
         true_from="2026-01-15", pub="2026-01-20T00:00:00Z", title="About"),
    page(d, "about", [f"{KS} is headquartered in Rotterdam.", f"{KS} was founded in 1995.",
                      f"The legal name of {KS} is {KS} GmbH."], epochs=(1,),
         true_from="2026-02-10", pub="2026-02-11T00:00:00Z", title="About"),
    page(d, "leadership", [f"{KS} CEO: Ulla Berg."], epochs=(0, 1), pub="2026-01-20T00:00:00Z",
         title="Leadership"),
    page(d, "team", [f"{KS} employs about 80 people."], epochs=(0, 1), pub="2026-01-05T22:00:00-03:00",
         title="Team"),
    page("wirecast-daily.test", "keystone-raise", [f"{KS} has raised $7M in funding."], kind="news",
         epochs=(0, 1), host="wirecast-daily.test", pub=None, title="Keystone raise"),
    page(d, "exec", [f"{KS} CTO: Per Lund."], epochs=(1,), true_from="2026-02-10", pub="2026-02-11T00:00:00Z",
         title="Executives"),
])


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
    import s2model
    corpus = s2model.load()
    DESIGN = {   # what stage-2.md gives for the stage-2 companies: (value, status, [values in rank order])
        "ashgrove-labs.test": {
            "legal_name": ("Ashgrove Labs, Inc.", "contested", ["Ashgrove Labs, Inc.", "Ashgrove Labs Holdings Ltd"]),
            "hq_city": ("Zagreb", "contested", ["Zagreb", "Århus"]),
            "ceo": ("Sam Ortiz", "contested", ["Sam Ortiz", "Dana Ruiz", "Pat Lee"]),
            "founded_year": (2011, "contested", [2011, 2010]),
            "headcount_range": ("201-500", "contested", ["201-500", "51-200"]),
            "funding_total": (9000000, "contested", [9000000, 10000000])},
        "brightmoor-energy.test": {
            "legal_name": ("Brightmoor Energy Ltd", "known", ["Brightmoor Energy Ltd"]),
            "hq_city": ("Bristol", "known", ["Bristol"]), "ceo": ("Ravi Menon", "known", ["Ravi Menon"]),
            "founded_year": (2003, "known", [2003]), "headcount_range": ("51-200", "known", ["51-200"]),
            "funding_total": (5000000, "known", [5000000])},
        "cobalt-harbor.test": {
            "ceo": ("Gus Hill", "contested", ["Gus Hill", "Ben Cole", "Ada Marsh", "Eve Ford", "Hal Ivey", "Cy Dunn", "Di Evans"])},
        "driftwood-games.test": {
            "ceo": ("Zed Quinn", "contested", ["Zed Quinn", "Amy Yu"]),
            "founded_year": (2012, "known", [2012, 2012, 2012]),
            "headcount_range": ("51-200", "known", ["51-200", "51-200"]),
            "funding_total": (12000000, "known", [12000000, 12000000]),
            "legal_name": (None, "unknown", []), "hq_city": (None, "unknown", [])}}
    for dom, fl in DESIGN.items():
        for name, (val, st, order) in fl.items():
            dd, exp, _ = s2model.expected_field(dom, name, 0, corpus)
            assert dd["exact"] and not exp["may"], (dom, name, exp)
            got = (dd["value"], dd["status"], [c["value"] for c in dd["order"]])
            assert got == (val, st, order), (dom, name, got, (val, st, order))
    print("ok", len(C), "companies; stage-2 design verified")
