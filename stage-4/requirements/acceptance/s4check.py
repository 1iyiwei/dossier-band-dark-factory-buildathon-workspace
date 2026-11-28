"""Stage-4 response checks, written from stage-4.md alone: the keys every field gains (`origins`, `corroborated`,
`corroborated_since`), candidate `origin`, and the `investors` field. Internal consistency of one response only
(what the response says about itself); comparisons with the corpus model are in conftest.check_origins and the
timeline tests (s4util.py)."""
from __future__ import annotations

import s2model as m
import s3model as s3

KEYS = ("origins", "corroborated", "corroborated_since")
CAND_KEYS_INV = m.CAND_KEYS | {"true_from", "learned_at"}


def is_domain(x):
    return isinstance(x, str) and m.valid_domain(x) == x


def check_origin_keys(name, fld, *, members=None, latest=None):
    """origins / corroborated / corroborated_since of one field. `members`: list of candidate lists, one per member
    (the candidates of the selected value, of an executive's (title, name), of an investor's name); None when the
    field is unknown. `latest`: the time of the build the response is from (an upper bound of corroborated_since)."""
    assert set(fld) >= set(KEYS), (name, sorted(fld))
    og, co, since = fld["origins"], fld["corroborated"], fld["corroborated_since"]
    assert isinstance(og, list) and og == sorted(set(og)) and all(is_domain(x) for x in og), (name, og)
    assert isinstance(co, bool), (name, co)
    for c in fld["candidates"]:
        assert "origin" in c and is_domain(c["origin"]), (name, c)
    if not members:
        assert og == [] and co is False and since is None, (name, og, co, since)
        return
    want = sorted({c["origin"] for cs in members for c in cs})
    assert og == want, f"{name}: origins {og} != distinct origins of the selected candidates {want}"
    assert co == all(len({c["origin"] for c in cs}) >= 2 for cs in members), \
        f"{name}: corroborated {co} for member origins {[sorted({c['origin'] for c in cs}) for cs in members]}"
    if co:
        assert since is not None, f"{name}: corroborated now, so it has had two standing origins: since is null"
    if since is not None:
        t = m.parse_rfc3339(since)
        assert t is not None, (name, since)
        if latest is not None:
            assert t <= latest, f"{name}: corroborated_since {since} after the build it is from"


def six_members(fld):
    cs = [c for c in fld["candidates"] if fld["value"] is not None and m.same_value(c["value"], fld["value"])]
    return [cs] if cs else None


def exec_members(fld):
    if fld["value"] is None:
        return None
    return [[c for c in fld["candidates"] if c["title"] == x["title"] and m.same_value(c["value"], x["name"])]
            for x in fld["value"]]


def inv_members_of(cands):
    """names that are members: one candidate of own/filing kind, or two or more distinct origins."""
    by = {}
    for c in cands:
        by.setdefault(c["value"], []).append(c)
    return {n: cs for n, cs in sorted(by.items())
            if any(c["kind"] in ("own", "filing") for c in cs) or len({c["origin"] for c in cs}) >= 2}


def inv_members(fld):
    if fld["value"] is None:
        return None
    return [[c for c in fld["candidates"] if c["value"] == n] for n in fld["value"]]


def check_inv_field(fld, *, retrieved_at=None):
    """The `investors` field of stage-4.md: members, value, status, candidates, citations, times, origin keys."""
    assert set(fld) >= {"value", "status", "true_from", "learned_at", "citations", "candidates"} | set(KEYS), sorted(fld)
    cands = fld["candidates"]
    for c in cands:
        assert set(c) >= CAND_KEYS_INV, sorted(c)
        assert "title" not in c, "an investors candidate has no title"
        assert isinstance(c["value"], str) and c["value"] == c["value"].strip() and c["value"], c
        assert c["provider"] in m.PROVIDERS and c["kind"] in (None,) + m.KINDS
        assert isinstance(c["selected"], bool)
        assert c["true_from"] is None or s3.valid_date(c["true_from"]) == c["true_from"], c
        assert m.parse_rfc3339(c["learned_at"]) is not None
        if retrieved_at is not None:
            assert m.parse_rfc3339(c["retrieved_at"]) == retrieved_at and m.parse_rfc3339(c["learned_at"]) <= retrieved_at
    pairs = [(c["url"], c["value"]) for c in cands]
    assert len(set(pairs)) == len(pairs), f"investors: a (page, name) is a candidate once: {pairs}"
    assert [m.rank_key(c) for c in cands] == sorted(m.rank_key(c) for c in cands), \
        "investors candidates must be listed in the order the selection rule ranks them"
    mem = inv_members_of(cands)
    if not mem:
        assert fld["value"] is None and fld["status"] == "unknown" and fld["citations"] == [] \
            and fld["true_from"] is None and fld["learned_at"] is None, fld
        assert not any(c["selected"] for c in cands), "no member: no candidate is selected"
        check_origin_keys("investors", fld, members=None)
        return
    assert fld["value"] == sorted(mem), f"investors value {fld['value']!r} != sorted members {sorted(mem)}"
    assert fld["status"] == "known", fld["status"]
    for c in cands:
        assert c["selected"] is (c["value"] in mem), f"selected must be true exactly on members' candidates: {c}"
    cites = [{"url": c["url"], "excerpt": c["excerpt"], "provider": c["provider"]}
             for n in sorted(mem) for c in cands if c["value"] == n]
    assert fld["citations"] == cites, (fld["citations"], cites)
    tfs = []
    for n in sorted(mem):
        vs = [c["true_from"] for c in cands if c["value"] == n and c["true_from"] is not None]
        tfs.append(min(vs) if vs else None)
    want = None if any(t is None for t in tfs) else max(tfs)
    assert fld["true_from"] == want, f"investors true_from {fld['true_from']!r}: latest of members' {tfs}"
    assert m.parse_rfc3339(fld["learned_at"]) is not None
    if retrieved_at is not None:
        assert m.parse_rfc3339(fld["learned_at"]) <= retrieved_at
    check_origin_keys("investors", fld, members=inv_members(fld), latest=retrieved_at)
