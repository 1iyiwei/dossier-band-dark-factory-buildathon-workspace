"""Stage-3 model, written from stage-3.md alone (and the stage-1/2 rules it builds on).

* `true_from` of a page (Two times per value);
* the candidates (six fields and the three executive titles) that the evidence of a corpus company
  supports in an epoch, from the corpus *browser text* (oracle.py = Appendix A);
* `executives` field derivation (members, status, true_from, citations);
* history / feed entries from the sequence of selected values of ready builds (Changes and
  corrections), including the executives typing;
* page versions, `as_of` and `values?true_at` (page version rules).

Checked offline by test_03_model_selfcheck.py; used by test_s3_*.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import lineage as lin
import oracle as o
import s2model as m

FIELDS = o.FIELDS                      # the six fields of stage-1 §4, in order
TITLES = o.TITLES                      # cfo, coo, cto
ALL = FIELDS + ("executives", "investors")     # stage 4: investors after executives
DATE = re.compile(r"^(\d{4})-(\d\d)-(\d\d)$")


# ------------------------------------------------------------------------- true_from of a page
def valid_date(s):
    """`YYYY-MM-DD` that is a real calendar date -> ISO string, else None (RULINGS 60)."""
    if not isinstance(s, str):
        return None
    mm = DATE.match(s.strip())
    if not mm:
        return None
    try:
        return date(int(mm[1]), int(mm[2]), int(mm[3])).isoformat()
    except ValueError:
        return None


def page_true_from(effective, published):
    """`Effective: <YYYY-MM-DD>` if valid, else the UTC date part of a valid `Published`, else None."""
    d = valid_date(effective)
    if d:
        return d
    t = m.parse_rfc3339(published) if published is not None else None
    return t.astimezone(timezone.utc).date().isoformat() if t else None


# ------------------------------------------------------------------------- candidates of an epoch
def expected_all(domain, epoch, corpus, research=True):
    """({name: {"must": {(url, value)}, "may": set()}} for the six fields, cfo/coo/cto and investors,
    {url: (kind, published datetime|None, true_from|None)}, {url: {name: {value: excerpt-sentence}}}).
    must: a whole sentence supports the value (investors: contains the name)."""
    res = {f: {"must": set(), "may": set()} for f in FIELDS + TITLES + ("investors",)}
    info, sents = {}, {}
    company = corpus.get(domain)
    if company is None:
        return res, info, sents
    for url, p in m.evidence_pages(company, epoch, research).items():
        info[url] = (m.kind_of(p, url, domain), m.page_published(p.get("published_at")),
                     page_true_from(p.get("true_from"), p.get("published_at")))
        sents[url] = {}
        for sent in o.sentences(m.browser_prose(p)):
            if not o.names_company(sent, domain):
                continue
            for f in FIELDS + TITLES:
                v = o.supported_values(sent, f, domain)
                if len(v) == 1:
                    val = next(iter(v))
                    res[f]["must"].add((url, val))
                    sents[url].setdefault(f, {})[val] = sent
                else:
                    for sp in o.spans(sent):
                        w = o.supported_values(sp, f, domain)
                        if len(w) == 1 and not any(o.has_phrase(sent, n) for n in o.NEGATING):
                            res[f]["may"].add((url, next(iter(w))))
            whole = o.investor_names(sent, domain)
            for val in whole:
                res["investors"]["must"].add((url, val))
                sents[url].setdefault("investors", {})[val] = sent
            if any(o.has_phrase(sent, p) for p in o.PHRASES["investors"]) \
                    and not any(o.has_phrase(sent, n) for n in o.NEGATING):
                for sp in o.spans(sent):          # a fragment may name an investor the whole sentence does not
                    for val in o.investor_names(sp, domain) - whole:
                        res["investors"]["may"].add((url, val))
    for f in res:
        res[f]["may"] -= res[f]["must"]
    return res, info, sents


def cand_dicts(name, pairs, info, origins=None):
    out = []
    for url, val in sorted(pairs, key=lambda t: (t[0], str(t[1]))):
        kind, pub, tf = info[url]
        out.append({"value": val, "url": url, "excerpt": "", "provider": "nimble", "kind": kind,
                    "published_at": pub.isoformat() if pub else None, "true_from": tf,
                    "origin": (origins or {}).get(url, m.host_of(url))})
    return out


def rank(cands):
    return sorted(cands, key=m.rank_key)


def field_of(name, cands):
    """The six-field derivation (value, status, order, selected candidate)."""
    d = m.derive(cands)
    d["selected"] = d["order"][0] if d["order"] else None
    return d


def exec_of(cands_by_title):
    """executives (stage-3.md Executives) from {title: [candidate dicts]} ->
    {value, status, true_from, members:[{title,name,true_from}], order:[(title, cand)], citations}."""
    members, order, contested = [], [], False
    for t in TITLES:
        cs = cands_by_title.get(t) or []
        if not cs:
            continue
        r = rank(cs)
        top = r[0]
        members.append({"title": t, "name": top["value"], "true_from": top["true_from"]})
        order += [(t, c) for c in r]
        if any(not m.same_value(c["value"], top["value"]) for c in r):
            contested = True
    if not members:
        return {"value": None, "status": "unknown", "true_from": None, "members": [], "order": [],
                "citations": []}
    tfs = [x["true_from"] for x in members]
    tf = None if any(x is None for x in tfs) else max(tfs)
    cites = []
    for x in members:
        for t, c in order:
            if t == x["title"] and m.same_value(c["value"], x["name"]):
                cites.append(c)
    return {"value": [{"title": x["title"], "name": x["name"]} for x in members],
            "status": "contested" if contested else "known", "true_from": tf, "members": members,
            "order": order, "citations": cites}


INVESTOR_KINDS = ("own", "filing")


def inv_of(cands):
    """investors (stage-4.md Investors) from the candidate dicts: members (sorted by name), value, status,
    true_from, the candidates in rank order, citations (members in value order, rank order within)."""
    byname = {}
    for c in cands:
        byname.setdefault(c["value"], []).append(c)
    members = []
    for n in sorted(byname):
        cs = byname[n]
        if any(c["kind"] in INVESTOR_KINDS for c in cs) or len({c["origin"] for c in cs}) >= 2:
            tfs = [c["true_from"] for c in cs if c["true_from"] is not None]
            members.append({"name": n, "true_from": min(tfs) if tfs else None,
                            "origins": {c["origin"] for c in cs}})
    order = rank(cands)
    if not members:
        return {"value": None, "status": "unknown", "true_from": None, "members": [], "order": order,
                "citations": []}
    tfs = [x["true_from"] for x in members]
    cites = [c for x in members for c in order if c["value"] == x["name"]]
    return {"value": [x["name"] for x in members], "status": "known",
            "true_from": None if any(t is None for t in tfs) else max(tfs), "members": members,
            "order": order, "citations": cites}


def member_origins(cands):
    """{field: [(member key, frozenset of origins of the member's candidates)]} in value order, for the eight fields:
    a six-field's member is its selected value, an executives member a (title, name), an investor a name."""
    out = {}
    for f in FIELDS:
        d = field_of(f, cands.get(f, []))
        out[f] = [] if d["selected"] is None else [(json_key(d["value"]), frozenset(
            c["origin"] for c in d["order"] if m.same_value(c["value"], d["value"])))]
    e = exec_of({t: cands.get(t, []) for t in TITLES})
    out["executives"] = [((x["title"], x["name"]), frozenset(
        c["origin"] for t, c in e["order"] if t == x["title"] and m.same_value(c["value"], x["name"])))
        for x in e["members"]]
    i = inv_of(cands.get("investors", []))
    out["investors"] = [(x["name"], frozenset(x["origins"])) for x in i["members"]]
    return out


def json_key(v):
    return ("i", v) if isinstance(v, int) and not isinstance(v, bool) else ("s", str(v).strip())


def selected_state(cands):
    """{field: {"value", "true_from", "urls": [citation urls in rank order], "status", "origins", "corroborated"}}
    for all eight fields from {name: [candidate dicts]} (six fields, titles and investors)."""
    out = {}
    for f in FIELDS:
        d = field_of(f, cands.get(f, []))
        sel = d["selected"]
        out[f] = {"value": d["value"], "status": d["status"], "true_from": sel["true_from"] if sel else None,
                  "urls": [c["url"] for c in d["order"] if m.same_value(c["value"], d["value"])]
                  if d["order"] else []}
    e = exec_of({t: cands.get(t, []) for t in TITLES})
    out["executives"] = {"value": e["value"], "status": e["status"], "true_from": e["true_from"],
                         "urls": [c["url"] for c in e["citations"]]}
    i = inv_of(cands.get("investors", []))
    out["investors"] = {"value": i["value"], "status": i["status"], "true_from": i["true_from"],
                        "urls": [c["url"] for c in i["citations"]]}
    mo = member_origins(cands)
    for f in ALL:
        origins = sorted(set().union(*[o_ for _, o_ in mo[f]])) if mo[f] else []
        out[f]["origins"] = origins
        out[f]["corroborated"] = bool(mo[f]) and all(len(o_) >= 2 for _, o_ in mo[f])
        out[f]["members_origins"] = mo[f]
    return out


# ------------------------------------------------------------------------- history / feed
def differs(a, b):
    if a is None or b is None:
        return (a is None) != (b is None)
    if isinstance(a, list):
        return a != b
    return not m.same_value(a, b)


def exec_members(v):
    return {x["title"]: x["name"] for x in v} if v else {}


def classify_field(old, new):
    """old/new: (value, true_from). 'correction' | 'change' (Changes and corrections table)."""
    (ov, otf), (nv, ntf) = old, new
    if ov is not None and nv is not None and otf is not None and ntf is not None and ntf <= otf:
        return "correction"
    return "change"


def classify_exec(old, new):
    """old/new: (members [{title,name,true_from}], ) lists. Typed by title."""
    om = {x["title"]: x for x in old}
    nm = {x["title"]: x for x in new}
    diff = [t for t in TITLES if (t in om) != (t in nm) or (t in om and om[t]["name"] != nm[t]["name"])]
    assert diff
    for t in diff:
        if not (t in om and t in nm and om[t]["true_from"] is not None and nm[t]["true_from"] is not None
                and nm[t]["true_from"] <= om[t]["true_from"]):
            return "change"
    return "correction"


def classify_inv(old, new):
    """investors (stage-4.md): old/new are (members [{name, true_from}], field true_from). A name in the new value and
    not in the earlier one counts as a correction when its true_from and the earlier value's true_from are both not
    null and its true_from is on or before the earlier value's. `correction` when every name in exactly one of the
    two values counts as one (a name only in the earlier value never does), else `change`."""
    (om, otf), (nm, ntf) = old, new
    on, nn = {x["name"] for x in om}, {x["name"]: x for x in nm}
    if on - set(nn):
        return "change"
    for n in set(nn) - on:
        tf = nn[n]["true_from"]
        if not (tf is not None and otf is not None and tf <= otf):
            return "change"
    return "correction"


@dataclass
class Build:
    """One ready build as the model sees it: its time and, per gathered URL, the page version."""
    time: datetime
    pages: dict = field(default_factory=dict)      # url -> (true_from|None, {name: [candidate dicts]})
    ready: bool = True

    def candidates(self):
        out = {}
        for url, (tf, by) in self.pages.items():
            for name, cs in by.items():
                out.setdefault(name, []).extend(cs)
        return out

    def state(self):
        return selected_state(self.candidates())


def page_origins(domain, epoch, corpus, research=True):
    """({url: origin} of the evidence pages of the epoch, [originals rule 2 needs])"""
    company = corpus.get(domain)
    if company is None:
        return {}, []
    return lin.origins_of_epoch(domain, epoch, corpus, m.evidence_pages(company, epoch, research))


def build_from_epoch(domain, epoch, time, corpus, research=True):
    must, info, _ = expected_all(domain, epoch, corpus, research)
    origins, _ = page_origins(domain, epoch, corpus, research)
    pages = {}
    for url in info:
        pages[url] = (info[url][2], {})
    for name in FIELDS + TITLES + ("investors",):
        for url, val in must[name]["must"]:
            kind, pub, tf = info[url]
            pages[url][1].setdefault(name, []).append(
                {"value": val, "url": url, "excerpt": "", "provider": "nimble", "kind": kind,
                 "published_at": pub.isoformat() if pub else None, "true_from": tf, "origin": origins[url]})
    return Build(time, pages)


def corroboration(builds):
    """stage-4.md `corroborated_since`: for each ready build i (builds in build order) and each of the eight fields,
    {"origins", "corroborated", "since": datetime|None} as the field of the dossier after build i. A member (the
    selected value; an executive's (title, name); an investor's name) has standing origins: the origins of its
    candidates gathered by the build after which it last became a member and every later ready build up to i.
    `since` is the time of the earliest ready build after which every current member has two or more."""
    states = [b.state() for b in builds]
    out = []
    for i, b in enumerate(builds):
        row = {}
        for f in ALL:
            cur = states[i][f]["members_origins"]
            ks = []
            for key, _ in cur:
                start = i
                while start > 0 and key in dict(states[start - 1][f]["members_origins"]):
                    start -= 1
                union, k_m = set(), None
                for j in range(start, i + 1):
                    union |= dict(states[j][f]["members_origins"])[key]
                    if len(union) >= 2 and k_m is None:
                        k_m = j
                ks.append(k_m)
            since = None if (not cur or any(k is None for k in ks)) else builds[max(ks)].time
            row[f] = {"origins": states[i][f]["origins"], "corroborated": states[i][f]["corroborated"],
                      "since": since}
        out.append(row)
    return out


def history(builds):
    """{field: [entry]} for ready builds in build order: entries typed initial/change/correction;
    entry = {type, value, true_from, learned_at (datetime), urls}. Also the feed entries (type
    change/correction) in feed order: (build_index, field, type, from, to, true_from, learned_at)."""
    hist = {f: [] for f in ALL}
    feed = []
    prev = None
    first = True
    for bi, b in enumerate(builds):
        st = b.state()
        for f in ALL:
            new = st[f]
            if first:
                if new["value"] is not None:
                    hist[f].append({"type": "initial", "value": new["value"], "true_from": new["true_from"],
                                    "learned_at": b.time, "urls": new["urls"]})
                continue
            old = prev[f]
            if not differs(old["value"], new["value"]):
                continue
            if f == "executives":
                if old["value"] is None or new["value"] is None:
                    typ = "change"
                else:
                    typ = classify_exec(prev_members(builds[bi - 1], old), prev_members(b, new))
            elif f == "investors":
                if old["value"] is None or new["value"] is None:
                    typ = "change"
                else:
                    typ = classify_inv((inv_of(builds[bi - 1].candidates().get("investors", []))["members"],
                                        old["true_from"]),
                                       (inv_of(b.candidates().get("investors", []))["members"], new["true_from"]))
            else:
                typ = classify_field((old["value"], old["true_from"]), (new["value"], new["true_from"]))
            hist[f].append({"type": typ, "value": new["value"],
                            "true_from": new["true_from"] if new["value"] is not None else None,
                            "learned_at": b.time, "urls": new["urls"] if new["value"] is not None else []})
            feed.append((bi, f, typ, old["value"], new["value"],
                         new["true_from"] if new["value"] is not None else None, b.time))
        prev = st
        first = False
    return hist, feed


def prev_members(b, st):
    e = exec_of({t: b.candidates().get(t, []) for t in TITLES})
    return e["members"]


# ------------------------------------------------------------------------- page versions
@dataclass
class Version:
    tf: str | None
    by: dict
    end: str | None = None


def versions_known(builds, as_of):
    """{url: [Version]} the versions of every URL known at as_of: ready builds with time <= as_of in
    build order (stage-3.md `values`): a later version replaces every earlier version of its URL
    whose true_from is on or after its own (all of them when its own is null); the latest earlier
    version it does not replace stops holding on its true_from."""
    per = {}
    for b in builds:
        if not b.ready or b.time > as_of:
            continue
        for url, (tf, by) in b.pages.items():
            lst = per.setdefault(url, [])
            if tf is None:
                lst.clear()
            else:
                lst[:] = [v for v in lst if v.tf is None or v.tf < tf]
                if lst:
                    lst[-1].end = tf
            lst.append(Version(tf, by))
    return per


def holds(v, d):
    return v.tf is not None and v.tf <= d and (v.end is None or d < v.end)


def values_at(builds, as_of, true_at):
    """{field: {"value", "true_from", "urls"}} for the seven fields."""
    cands = {}
    for url, lst in versions_known(builds, as_of).items():
        for v in lst:
            if holds(v, true_at):
                for name, cs in v.by.items():
                    cands.setdefault(name, []).extend(cs)
    st = selected_state(cands)
    return {f: {"value": st[f]["value"], "true_from": st[f]["true_from"], "urls": st[f]["urls"]}
            for f in ALL}


def as_of_build(builds, as_of):
    """Index of the build an `as_of` answers with: the last ready build whose time is at or before
    as_of (the last in build order among equal times), or None."""
    idx = None
    for i, b in enumerate(builds):
        if b.ready and b.time <= as_of:
            idx = i
    return idx


def utc(s):
    return m.parse_rfc3339(s)


# ------------------------------------------------------------------------- response shape checks
def _times_ok(c, retrieved_at, who):
    assert "true_from" in c and "learned_at" in c, (who, sorted(c))
    assert c["true_from"] is None or valid_date(c["true_from"]) == c["true_from"], (who, c["true_from"])
    la = m.parse_rfc3339(c["learned_at"])
    assert la is not None, (who, c["learned_at"])
    if retrieved_at is not None:
        assert la <= retrieved_at, f"{who}: learned_at {c['learned_at']} after retrieved_at"


def check_field_times(name, fld, *, retrieved_at=None):
    """Two times per value: each candidate and the field carry true_from (date or null) and learned_at."""
    assert "true_from" in fld and "learned_at" in fld, (name, sorted(fld))
    for c in fld["candidates"]:
        _times_ok(c, retrieved_at, name)
    if fld["value"] is None:
        assert fld["true_from"] is None and fld["learned_at"] is None, (name, fld)
        return
    assert fld["true_from"] is None or valid_date(fld["true_from"]) == fld["true_from"], (name, fld["true_from"])
    assert m.parse_rfc3339(fld["learned_at"]) is not None, (name, fld["learned_at"])
    assert fld["true_from"] == fld["candidates"][0]["true_from"], \
        f"{name}: a selected value's true_from is that of its selected candidate"
    if retrieved_at is not None:
        assert m.parse_rfc3339(fld["learned_at"]) <= retrieved_at, (name, fld["learned_at"])


def check_exec_field(fld, *, retrieved_at=None):
    """The `executives` field of stage-3.md: members, candidates by title, status, citations, times."""
    assert set(fld) >= {"value", "status", "true_from", "learned_at", "citations", "candidates"}, sorted(fld)
    cands = fld["candidates"]
    if fld["value"] is None:
        assert fld == {"value": None, "status": "unknown", "true_from": None, "learned_at": None,
                       "citations": [], "candidates": []} or (
            fld["status"] == "unknown" and fld["citations"] == [] and cands == []
            and fld["true_from"] is None and fld["learned_at"] is None), fld
        return
    assert fld["status"] in ("known", "contested"), fld["status"]
    keys = m.CAND_KEYS | {"title", "true_from", "learned_at"}
    for c in cands:
        assert set(c) >= keys, sorted(c)
        assert c["title"] in TITLES and isinstance(c["value"], str) and c["value"] == c["value"].strip() and c["value"]
        _times_ok(c, retrieved_at, c["title"])
    pairs = [(c["title"], c["url"], c["value"]) for c in cands]
    assert len(set(pairs)) == len(pairs), f"a (title, page, name) is a candidate once: {pairs}"
    # candidates: by title in the order cfo, coo, cto, then in rank order
    titles = [c["title"] for c in cands]
    assert titles == sorted(titles, key=TITLES.index), f"candidates must be listed by title: {titles}"
    members = []
    contested = False
    for t in TITLES:
        cs = [c for c in cands if c["title"] == t]
        if not cs:
            continue
        assert [m.rank_key(c) for c in cs] == sorted(m.rank_key(c) for c in cs), f"{t}: not in rank order"
        assert [c["selected"] for c in cs] == [True] + [False] * (len(cs) - 1), f"{t}: selected on the first only"
        members.append((t, cs[0]))
        contested |= any(not m.same_value(c["value"], cs[0]["value"]) for c in cs)
    assert [{"title": t, "name": c["value"]} for t, c in members] == fld["value"], (fld["value"], members)
    assert all(set(x) == {"title", "name"} for x in fld["value"])
    assert fld["status"] == ("contested" if contested else "known"), fld["status"]
    cites = []
    for t, top in members:
        for c in cands:
            if c["title"] == t and m.same_value(c["value"], top["value"]):
                cites.append({"url": c["url"], "excerpt": c["excerpt"], "provider": c["provider"]})
    assert fld["citations"] == cites, (fld["citations"], cites)
    tfs = [c["true_from"] for _, c in members]
    want = None if any(x is None for x in tfs) else max(tfs)
    assert fld["true_from"] == want, f"executives true_from {fld['true_from']!r}: latest of members' {tfs}"
    assert m.parse_rfc3339(fld["learned_at"]) is not None
    if retrieved_at is not None:
        assert m.parse_rfc3339(fld["learned_at"]) <= retrieved_at
