"""Black-box acceptance helpers for Dossier stage 2 (stage-1 helpers carried forward).

Environment:
  BASE_URL          the service under test (required)
  MOCK_URL          the mock web admin/log endpoint, serving ./corpus (required for provider tests)
  MOCK_ADMIN_TOKEN  admin token of that mock (default local-admin)
  BASE_URL_2        optional second, fresh instance of the same image (cross-instance import)
  BASE_URL_S1       optional running *stage-1* service (the team's final stage-1 image) wired to the
                    same mock: enables the stage-1 -> stage-2 export/import upgrade tests
  HEADED=1          show the browser in the UI tests
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import oracle as o  # noqa: E402
import s2model as m  # noqa: E402

HERE = pathlib.Path(__file__).parent
BASE = os.environ.get("BASE_URL", "").rstrip("/")
MOCK = os.environ.get("MOCK_URL", "").rstrip("/")
MOCK_TOKEN = os.environ.get("MOCK_ADMIN_TOKEN", "local-admin")
BASE2 = os.environ.get("BASE_URL_2", "").rstrip("/")
BASE_S1 = os.environ.get("BASE_URL_S1", "").rstrip("/")
CORPUS_S2 = m.load()
NOW0 = "2026-03-01T09:00:00+00:00"
PW = "correct horse"
FIELDS = o.FIELDS
EXPECT = json.loads((HERE / "expectations.json").read_text(encoding="utf-8"))
RFC3339 = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)$")
NOBODY = object()
JSON_CT = re.compile(r"^application/json\s*;\s*charset=utf-?8$", re.I)
ADA = {"id": "u_ada", "email": "ada@example.com", "password": PW, "display_name": "Ada"}
BOB = {"id": "u_bob", "email": "bob@example.com", "password": PW, "display_name": "Bob"}


def fixture(now=NOW0, users=(ADA, BOB)):
    return {"now": now, "users": [dict(u) for u in users]}


def new_key():
    return "k-" + uuid.uuid4().hex


def parse_ts(s):
    assert isinstance(s, str) and RFC3339.match(s), f"not RFC 3339 with offset: {s!r}"
    return datetime.fromisoformat(s)


class Api:
    def __init__(self, base, token=None, timeout=5.0):
        self.base, self.token = base, token
        self.c = httpx.Client(base_url=base, timeout=timeout)

    def req(self, method, path, *, body=NOBODY, raw=None, key=None, token=..., headers=None,
            params=None, timeout=None):
        h = dict(headers or {})
        tok = self.token if token is ... else token
        if tok is not None:
            h.setdefault("Authorization", f"Bearer {tok}")
        if key is not None:
            h["Idempotency-Key"] = key
        kw = {"headers": h}
        if raw is not None:
            h.setdefault("Content-Type", "application/json")
            kw["content"] = raw
        elif body is not NOBODY:
            h.setdefault("Content-Type", "application/json")
            kw["content"] = json.dumps(body)
        if params is not None:
            kw["params"] = params
        if timeout:
            kw["timeout"] = timeout
        r = self.c.request(method, path, **kw)
        assert r.status_code < 500, f"CV-10 5xx: {method} {path} -> {r.status_code} {r.text[:200]}"
        return r

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def post(self, path, **kw):
        return self.req("POST", path, **kw)

    def as_token(self, token):
        return Api(self.base, token, self.c.timeout.read)


def assert_status(r, status):
    assert r.status_code == status, f"{r.request.method} {r.request.url} -> {r.status_code} " \
                                    f"{r.text[:300]!r} (wanted {status})"
    return r


def check_error_envelope(r):
    assert JSON_CT.match(r.headers.get("content-type", "")), r.headers.get("content-type")
    j = r.json()
    assert isinstance(j, dict) and set(j) == {"error"} and isinstance(j["error"], dict), j
    assert isinstance(j["error"].get("code"), str) and isinstance(j["error"].get("message"), str)
    return j["error"]["code"]


def err(r, status, code):
    assert_status(r, status)
    got = check_error_envelope(r)
    assert got == code, f"code {got!r} != {code!r}: {r.text[:200]}"


def ok_json(r, status=200):
    assert_status(r, status)
    assert JSON_CT.match(r.headers.get("content-type", "")), r.headers.get("content-type")
    return r.json()


class Mock:
    def __init__(self, url, token):
        self.c = httpx.Client(base_url=url, headers={"X-Mock-Admin": token}, timeout=10)
        self.epoch_now = 0

    def reset(self, epoch=0):
        assert self.c.post("/_mock/reset", json={"epoch": epoch}).status_code == 204
        self.epoch_now = epoch

    def epoch(self, n):
        assert self.c.post("/_mock/epoch", json={"epoch": n}).status_code == 204
        self.epoch_now = n

    def fault(self, provider, methods, mode, seconds=None):
        body = {"provider": provider, "methods": methods, "mode": mode}
        if seconds is not None:
            body["seconds"] = seconds
        r = self.c.post("/_mock/faults", json=body)
        assert r.status_code == 204, r.text

    def clear(self):
        for p in ("nimble", "tavily"):
            self.fault(p, ["search", "extract", "research"], "none")

    def break_all(self, providers=("nimble", "tavily")):
        for p in providers:
            self.fault(p, ["search", "extract", "research"], "error")

    def log(self):
        return self.c.get("/_mock/log").json()["calls"]


class World:
    def __init__(self, mock):
        self.mock = mock
        self.anon = Api(BASE)
        self.ada = self.bob = None

    def reset(self, fx=None, mock_epoch=0):
        r = self.anon.post("/_test/reset", body=fx or fixture(), timeout=10)
        assert_status(r, 204)
        assert r.content in (b"", None)
        if self.mock:
            self.mock.reset(mock_epoch)
        emails = {u["email"] for u in (fx or fixture())["users"]}
        self.ada = self.login(ADA) if ADA["email"] in emails else None
        self.bob = self.login(BOB) if BOB["email"] in emails else None

    def login(self, user):
        r = self.anon.post("/auth/login", body={"email": user["email"], "password": user["password"]})
        return Api(BASE, ok_json(r)["token"])

    def clock(self, now):
        return self.anon.post("/_test/clock", body={"now": now})

    def signup(self, email, password=PW, name="Zed"):
        return self.anon.post("/auth/signup", body={"email": email, "password": password,
                                                    "display_name": name})

    def request(self, api, domain, key=None):
        return api.post("/dossiers", body={"domain": domain}, key=key or new_key())

    def dossier(self, api, domain):
        return ok_json(api.get(f"/dossiers/{domain}"))

    def wait(self, api, domain, timeout=20, interval=0.1):
        t0 = time.time()
        while True:
            b = self.dossier(api, domain)
            if b["state"] != "building":
                return b
            assert time.time() - t0 < timeout, f"still building after {timeout}s: {b['state']}"
            time.sleep(interval)

    def build(self, api, domain, timeout=20):
        """Start the first build and wait for it; returns (body, calls of this window)."""
        mark = len(self.mock.log())
        assert_status(self.request(api, domain), 202)
        body = self.wait(api, domain, timeout)
        return body, self.mock.log()[mark:]

    def refresh(self, api, domain, key=None, timeout=20):
        mark = len(self.mock.log())
        assert_status(api.post(f"/dossiers/{domain}/refresh", key=key or new_key()), 202)
        body = self.wait(api, domain, timeout)
        return body, self.mock.log()[mark:]


@pytest.fixture
def mock():
    if not MOCK:
        pytest.fail("MOCK_URL is required for provider-dependent tests (see README.md)")
    return Mock(MOCK, MOCK_TOKEN)


@pytest.fixture
def world(request):
    if not BASE:
        pytest.fail("BASE_URL is required")
    m = Mock(MOCK, MOCK_TOKEN) if MOCK else None
    w = World(m)
    w.reset()
    return w


@pytest.fixture
def pworld(world, mock):
    """A world whose mock web is guaranteed (provider tests)."""
    world.mock = mock
    world.reset()
    return world


def pmap(fn, items, workers=50):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))


# ------------------------------------------------------------ dossier verification
def check_shape(b):
    """Stage-2 dossier shape: stage-1 shape + candidates, three statuses (stage-2.md Status)."""
    assert set(b) >= {"dossier_id", "domain", "state", "researched_at", "spent_units", "fields"}, b
    assert isinstance(b["dossier_id"], str) and 1 <= len(b["dossier_id"]) <= 64
    assert b["state"] in ("building", "ready", "failed")
    assert isinstance(b["spent_units"], int) and not isinstance(b["spent_units"], bool) \
        and b["spent_units"] >= 0
    if b["researched_at"] is not None:
        parse_ts(b["researched_at"])
    assert list(sorted(b["fields"])) == sorted(FIELDS), list(b["fields"])
    ra = parse_ts(b["researched_at"]) if b["researched_at"] else None
    for name, fld in b["fields"].items():
        assert set(fld) >= {"value", "status", "citations", "candidates"}, (name, sorted(fld))
        assert fld["status"] in ("known", "contested", "unknown"), (name, fld["status"])
        if fld["value"] is None:
            assert fld["status"] == "unknown" and fld["citations"] == [] \
                and fld["candidates"] == [], (name, fld)
        else:
            assert fld["status"] in ("known", "contested") and len(fld["citations"]) >= 1, (name, fld)
        v = fld["value"]
        if name in ("founded_year", "funding_total") and v is not None:
            assert isinstance(v, int) and not isinstance(v, bool), (name, v)
        if name == "headcount_range" and v is not None:
            assert v in [r[0] for r in o.RANGES], v
        if name in ("legal_name", "hq_city", "ceo") and v is not None:
            assert isinstance(v, str) and v == v.strip() and v, (name, v)
        for c in fld["citations"]:
            assert set(c) >= {"url", "excerpt", "provider"}, c
            assert c["provider"] in m.PROVIDERS
        m.check_field_consistency(name, fld, retrieved_at=ra)


def served_index(calls):
    idx = {}
    for c in calls:
        for s in c["served"]:
            idx.setdefault(s["url"], []).append((c["provider"], s["text"]))
    return idx


def browser_prose_ok(domain, url, ex, epoch=None):
    """The excerpt is in the page's text as a browser shows it (stage-2.md Page text), for a page
    of the corpus; True for pages the corpus does not know (nothing to compare)."""
    comp = CORPUS_S2.get(domain)
    if comp is None:
        return True
    ents = [p for p in comp["pages"] if p["url"] == url and (epoch is None or epoch in p["epochs"])]
    if not ents:
        return True
    cex = o.collapse(ex)
    return any(cex in o.collapse(p["text"]) for p in ents)


def check_citation(domain, field, value, c, idx, epoch=None):
    ex = c["excerpt"]
    assert isinstance(ex, str) and 1 <= len(ex) <= 500, f"excerpt length {len(ex)}"
    cex = o.collapse(ex)
    hits = [(p, t) for p, t in idx.get(c["url"], []) if p == c["provider"]]
    assert hits, f"no text was served by {c['provider']} for {c['url']}: citation invented"
    found = [t for _, t in hits if cex in o.collapse(o.prose_of(t))]
    assert found, f"excerpt not (whitespace-insensitively) in the prose served for {c['url']}: {ex!r}"
    assert browser_prose_ok(domain, c["url"], ex, epoch), \
        f"excerpt is not in the text a browser shows for {c['url']} (stale served text?): {ex!r}"
    assert o.supports(ex, field, value, domain), \
        f"excerpt does not support {field}={value!r} by Appendix A: {ex!r} (reads as " \
        f"{o.supported_values(ex, field, domain)})"
    for t in found:   # context-faithful: not cut out of a hedged/negated sentence
        for sent in o.sentences(o.prose_of(t)):
            if cex in o.collapse(sent):
                assert not any(o.has_phrase(sent, n) for n in o.NEGATING), \
                    f"citation is a fragment of a negated/hedged sentence: {sent!r}"


def check_citations(b, calls_all, epoch=None):
    idx = served_index(calls_all)
    for name, fld in b["fields"].items():
        for c in fld["citations"]:
            check_citation(b["domain"], name, fld["value"], c, idx, epoch)
        for c in fld["candidates"]:
            check_citation(b["domain"], name, c["value"], c, idx, epoch)


def check_candidates(b, epoch=0, exact=True):
    """Every candidate carries its page's kind and publication time; the candidate set holds every
    value the evidence supports (once per page) and nothing the evidence does not; when no
    fragment-only value is possible the selected value is the one the rule picks (stage-2.md)."""
    dom = b["domain"]
    if b["state"] != "ready" and b["researched_at"] is None:
        return
    exp, info = m.expected_candidates(dom, epoch, CORPUS_S2)
    for name, fld in b["fields"].items():
        got = {(c["url"], c["value"]) for c in fld["candidates"]}
        must, may = exp[name]["must"], exp[name]["may"]
        assert must <= got, f"{dom} {name}: candidates missing {sorted(must - got, key=str)}"
        assert got <= must | may, f"{dom} {name}: unsupported candidates {sorted(got - must - may, key=str)}"
        for c in fld["candidates"]:
            kind, pub = info[c["url"]]
            assert c["kind"] == kind, f"{dom} {name} {c['url']}: kind {c['kind']!r} != {kind!r}"
            if pub is None:
                assert c["published_at"] is None, (c["url"], c["published_at"])
            else:
                assert c["published_at"] is not None and m.parse_rfc3339(c["published_at"]) == pub, \
                    (c["url"], c["published_at"], pub)
        if exact and not may:
            d, _, _ = m.expected_field(dom, name, epoch, CORPUS_S2)
            assert fld["value"] == d["value"] and fld["status"] == d["status"], \
                f"{dom} {name}: {fld['value']!r}/{fld['status']} expected {d['value']!r}/{d['status']}"
            assert [(c["url"], c["value"]) for c in fld["candidates"]] == \
                [(c["url"], c["value"]) for c in d["order"]], \
                f"{dom} {name}: candidate order {[(c['url'], c['value']) for c in fld['candidates']]}"


def check_expect(b, epoch=0):
    exp = EXPECT[b["domain"]][str(epoch)]
    for name, lab in exp.items():
        fld = b["fields"][name]
        if lab[0] == "K":
            assert fld["status"] == "known", f"{name} should be known ({lab[1]}), got {fld}"
            assert fld["value"] in lab[1], f"{name}={fld['value']!r} not one of {lab[1]}"
        elif lab[0] == "U":
            assert fld["status"] == "unknown", f"{name} must be unknown, got {fld}"
        elif fld["value"] is not None:
            pass  # F: free, citations are still checked strictly


def check_build(b, calls_all, epoch=0):
    check_shape(b)
    check_citations(b, calls_all, epoch)
    if b["domain"] in EXPECT and b["state"] == "ready":
        check_expect(b, epoch)
    if b["state"] == "ready":
        check_candidates(b, epoch)


def successful(calls):
    return [c for c in calls if c["status"] < 400]


def domain_searches(calls, domain):
    return [c for c in successful(calls) if c["method"] == "search" and c["query"] == domain]


_REPORT = []


@pytest.fixture
def ratio():
    def rec(label, body):
        known = sum(1 for f in body["fields"].values() if f["status"] == "known")
        _REPORT.append((label, known, body["spent_units"]))
    return rec


def pytest_terminal_summary(terminalreporter):
    if _REPORT:
        terminalreporter.write_sep("-", "fields known per unit spent (plausibility read)")
        for label, k, u in _REPORT:
            terminalreporter.write_line(f"{label:40s} known={k}/6 spent={u} "
                                        f"({(k / u if u else 0):.3f} fields/unit)")
