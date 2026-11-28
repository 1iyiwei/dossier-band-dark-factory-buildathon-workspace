"""Stage-2 model, written from stage-2.md alone: the selection rule, field status, page kind and
publication time, and the candidates the evidence of a corpus company supports (computed with
oracle.py, the independent Appendix A implementation, from the corpus *browser text*).

Used by conftest/test_s2_*.py and checked offline by test_02_selection_selfcheck.py.
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import oracle as o

HERE = pathlib.Path(__file__).parent
CORPUS = HERE / "corpus"
FIELDS = o.FIELDS
KINDS = ("own", "filing", "news", "aggregator")
PROVIDERS = ("nimble", "tavily", "kernel", "browserbase")
AUTHORITY = {"own": 0, "filing": 0, "news": 1, "aggregator": 2, None: 2}   # imported: null kind
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
RFC3339 = re.compile(r"^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(\.\d+)?(Z|[+-]\d\d:\d\d)$")


def parse_rfc3339(s):
    """aware datetime for an RFC 3339 timestamp (explicit offset required), else None."""
    if not isinstance(s, str) or not RFC3339.match(s):
        return None
    try:
        return datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
    except ValueError:
        return None


def micros(t):
    return (t - EPOCH) // timedelta(microseconds=1)


def normalise_domain(d):
    d = d.strip().lower()
    d = d[:-1] if d.endswith(".") else d
    return d[4:] if d.startswith("www.") else d


def host_of(url):
    return normalise_domain(urlsplit(url).hostname or "")


LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def valid_domain(s):
    """stage-1 §4: the normalised domain if it is a valid host name, else None (header domains: stage-4.md)."""
    if not isinstance(s, str):
        return None
    d = normalise_domain(s)
    if len(d) > 253 or len(d.split(".")) < 2 or not all(LABEL.match(x) for x in d.split(".")):
        return None
    return d


def registrant_of(entry, url):
    """stage-4.md Lineage header lines: the normalised `Registrant` domain; without a valid one, the host of the
    page's own URL (normalised)."""
    r = valid_domain(((entry or {}).get("lineage") or {}).get("registrant"))
    return r or host_of(url)


def page_kind(header_kind, url, domain, registrant=None):
    """stage-2.md 'Page kind' with stage-4.md 'Own pages': a listed Kind value, except that `own` only holds when the
    page's registrant is the company's domain (else aggregator); with no listed value, own on the company's host
    (and registrant) and aggregator otherwise. `registrant` defaults to the host of the URL."""
    reg = registrant if registrant is not None else host_of(url)
    if header_kind in KINDS:
        return "aggregator" if header_kind == "own" and reg != domain else header_kind
    return "own" if host_of(url) == domain and reg == domain else "aggregator"


def kind_of(entry, url, domain):
    return page_kind(entry.get("kind"), url, domain, registrant_of(entry, url))


def page_published(header_value):
    """Instant of a valid RFC 3339 Published value, else None."""
    return parse_rfc3339(header_value) if header_value is not None else None


# ------------------------------------------------------------------ the selection rule
def value_key(v):
    return (0, v) if isinstance(v, int) and not isinstance(v, bool) else (1, str(v).strip())


def rank_key(c):
    """Smaller sorts first = ranks higher (stage-2.md 'The selection rule')."""
    t = parse_rfc3339(c.get("published_at"))
    return (AUTHORITY[c.get("kind")],
            0 if t else 1, -micros(t) if t else 0,
            c["url"],
            PROVIDERS.index(c["provider"]),
            value_key(c["value"]))


def same_value(a, b):
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return type(a) is type(b) and a == b


def derive(cands):
    """{value, status, citations, order} that the rule and Status table give for candidates."""
    if not cands:
        return {"value": None, "status": "unknown", "citations": [], "order": []}
    order = sorted(cands, key=rank_key)
    top = order[0]["value"]
    status = "known" if all(same_value(c["value"], top) for c in order) else "contested"
    cites = [{"url": c["url"], "excerpt": c["excerpt"], "provider": c["provider"]}
             for c in order if same_value(c["value"], top)]
    return {"value": top, "status": status, "citations": cites, "order": order}


CAND_KEYS = {"value", "url", "excerpt", "provider", "kind", "published_at", "retrieved_at",
             "selected", "origin"}


def check_field_consistency(name, fld, *, retrieved_at=None):
    """The field's candidates/value/status/citations agree with each other by the rule."""
    assert set(fld) >= {"value", "status", "citations", "candidates"}, (name, sorted(fld))
    cands = fld["candidates"]
    assert isinstance(cands, list), (name, cands)
    for c in cands:
        assert set(c) >= CAND_KEYS, (name, sorted(c))
        assert c["provider"] in PROVIDERS, c
        assert c["kind"] is None or c["kind"] in KINDS, c
        assert c["published_at"] is None or parse_rfc3339(c["published_at"]), c
        assert parse_rfc3339(c["retrieved_at"]), c
        assert isinstance(c["selected"], bool), c
        assert isinstance(c["excerpt"], str) and 1 <= len(c["excerpt"]) <= 500, c
        if retrieved_at is not None:
            assert parse_rfc3339(c["retrieved_at"]) == retrieved_at, (c["retrieved_at"], retrieved_at)
        if name in ("founded_year", "funding_total"):
            assert isinstance(c["value"], int) and not isinstance(c["value"], bool), c
        else:
            assert isinstance(c["value"], str) and c["value"] == c["value"].strip() and c["value"], c
    pairs = [(c["url"], json.dumps(c["value"])) for c in cands]
    assert len(set(pairs)) == len(pairs), f"{name}: a (page, value) is a candidate once: {pairs}"
    d = derive(cands)
    assert [rank_key(c) for c in cands] == sorted(rank_key(c) for c in cands), \
        f"{name}: candidates not in selection-rule order: " \
        f"{[(c['value'], c['kind'], c['published_at'], c['url']) for c in cands]}"
    if not cands:
        assert fld["value"] is None and fld["status"] == "unknown" and fld["citations"] == [], \
            (name, fld)
        return d
    assert [c["selected"] for c in cands] == [True] + [False] * (len(cands) - 1), \
        f"{name}: selected must be true on the first candidate only"
    assert fld["value"] == d["value"] and type(fld["value"]) is type(d["value"]), \
        (name, fld["value"], d["value"])
    assert fld["status"] == d["status"], (name, fld["status"], d["status"])
    assert fld["citations"] == d["citations"], (name, fld["citations"], d["citations"])
    return d


# ------------------------------------------------------------------ the corpus, as a browser shows it
def load():
    out = {}
    for f in sorted(CORPUS.glob("*.test.json")):
        out[f.name[:-5]] = json.loads(f.read_text(encoding="utf-8"))
    return out


def page_entry(company, url, epoch):
    for p in company["pages"]:
        if p["url"] == url and epoch in p["epochs"]:
            return p
    return None


def browser_prose(entry):
    """The text a browser shows once loaded (corpus `text`); static_text is what search/extract
    serve and may be stale."""
    return entry["text"]


def evidence_pages(company, epoch, research=True):
    """Pages of the evidence: searchable pages of the epoch + pages nimble research cites."""
    out = {}
    for p in company["pages"]:
        if epoch in p["epochs"] and p.get("searchable", True):
            out[p["url"]] = p
    if research:
        for claim in company.get("research", {}).get("nimble", {}).get(str(epoch), []):
            p = page_entry(company, claim["url"], epoch)
            if p:
                out[p["url"]] = p
    return out


def expected_candidates(domain, epoch=0, corpus=None, research=True):
    """{field: {"must": {(url, value)}, "may": {(url, value)}, "info": {url: (kind, published)}}}.
    must: a whole sentence of the page's browser prose supports the value (A.2);
    may: only a fragment of a sentence supports it (context-faithful citations exclude negated
    sentences, so tests accept but never require these)."""
    corpus = corpus if corpus is not None else load()
    res = {f: {"must": set(), "may": set()} for f in FIELDS}
    info = {}
    company = corpus.get(domain)
    if company is None:
        return res, info
    for url, p in evidence_pages(company, epoch, research).items():
        info[url] = (kind_of(p, url, domain), page_published(p.get("published_at")))
        for sent in o.sentences(browser_prose(p)):
            if not o.names_company(sent, domain):
                continue
            for f in FIELDS:
                v = o.supported_values(sent, f, domain)
                if len(v) == 1:
                    res[f]["must"].add((url, next(iter(v))))
                else:
                    for sp in o.spans(sent):
                        w = o.supported_values(sp, f, domain)
                        if len(w) == 1 and not any(o.has_phrase(sent, n) for n in o.NEGATING):
                            res[f]["may"].add((url, next(iter(w))))
    for f in FIELDS:
        res[f]["may"] -= res[f]["must"]
    return res, info


def expected_field(domain, name, epoch=0, corpus=None, research=True):
    """derive() over the must-candidates, exact only when the field has no 'may' candidates."""
    exp, info = expected_candidates(domain, epoch, corpus, research)
    must = exp[name]["must"]
    cands = [{"value": v, "url": u, "excerpt": "", "provider": "nimble",
              "kind": info[u][0], "published_at": info[u][1].isoformat() if info[u][1] else None}
             for u, v in sorted(must, key=lambda t: (t[0], json.dumps(t[1])))]
    d = derive(cands)
    d["exact"] = not exp[name]["may"]
    return d, exp[name], info
