"""Stage 2 'Existing clients after an upgrade': a stage-2 service accepts the export of the team's
own stage-1 service (BASE_URL_S1, wired to the same mock). IDs (S2-UP-*) in ../LEDGER.md.

The stage-1 service builds dossiers from the mock; its export is imported into the stage-2 service
(BASE_URL); every claim below is checked against what the mock logged as served to that build."""
import json
import os
import pathlib
import time
from types import SimpleNamespace

import pytest

import oracle as o
import s2model as m
from conftest import (UNKNOWN, six, BASE, BASE_S1, FIELDS, MOCK, MOCK_TOKEN, NOW0, ADA, BOB, Api, Mock, PW,
                      assert_status, err, fixture, new_key, ok_json, parse_ts, CORPUS_S2)

DOMS = ["northwind-optics.test", "tidewell-pharma.test", "bluefin-marine.test"]
FAILED = "harbor-signal.test"


def served_support(domain, calls):
    """{field: {(url, value): [(provider, sentence)]}}: every value the text served to a build supports."""
    out = {f: {} for f in FIELDS}
    for c in calls:
        if c["status"] >= 400:
            continue
        for it in c["served"]:
            for sent in o.sentences(o.prose_of(it["text"])):
                for f in FIELDS:
                    v = o.supported_values(sent, f, domain)
                    if len(v) == 1:
                        out[f].setdefault((it["url"], next(iter(v))), []).append((c["provider"], sent))
    return out


def wait_state(api, d, timeout=40):
    t0 = time.time()
    while True:
        b = ok_json(api.get(f"/dossiers/{d}"))
        if b["state"] != "building":
            return b
        assert time.time() - t0 < timeout, "still building"
        time.sleep(0.2)


@pytest.fixture(scope="module")
def up():
    if not (BASE and BASE_S1 and MOCK):
        pytest.skip("BASE_URL, BASE_URL_S1 and MOCK_URL are needed (run.sh sets them)")
    mock = Mock(MOCK, MOCK_TOKEN)
    anon1, anon2 = Api(BASE_S1), Api(BASE)
    fx = fixture()
    assert_status(anon1.post("/_test/reset", body=fx, timeout=10), 204)
    assert_status(anon2.post("/_test/reset", body=fx, timeout=10), 204)
    mock.reset(0)
    login = lambda a, u: Api(a.base, ok_json(a.post("/auth/login", body={"email": u["email"], "password": u["password"]}))["token"])
    ada1, bob1 = login(anon1, ADA), login(anon1, BOB)
    zed = ok_json(anon1.post("/auth/signup", body={"email": "zed@example.com", "password": "zed-password-1",
                                                   "display_name": "Zed"}), 201)
    u = SimpleNamespace(mock=mock, anon1=anon1, anon2=anon2, ada1=ada1, bob1=bob1, zed=zed,
                        keys={}, first={}, windows={}, before={})
    for d in DOMS:
        u.keys[d] = new_key()
        mark = len(mock.log())
        u.first[d] = ok_json(ada1.post("/dossiers", body={"domain": d}, key=u.keys[d]), 202)
        wait_state(ada1, d)
        if d == "tidewell-pharma.test":          # the *last* ready build is the refresh
            u.refresh_key = new_key()
            mark = len(mock.log())
            u.refreshed = ok_json(ada1.post(f"/dossiers/{d}/refresh", key=u.refresh_key), 202)
            wait_state(ada1, d)
        time.sleep(0.5)
        u.windows[d] = mock.log()[mark:]
    mock.break_all()
    u.failed_key = new_key()
    u.failed_first = ok_json(ada1.post("/dossiers", body={"domain": FAILED}, key=u.failed_key), 202)
    assert wait_state(ada1, FAILED)["state"] == "failed"
    mock.clear()
    for d in DOMS + [FAILED]:
        u.before[d] = ok_json(ada1.get(f"/dossiers/{d}"))
    u.list_before = ok_json(ada1.get("/dossiers"))["dossiers"]
    exp = anon1.get("/_test/export")
    assert exp.status_code == 200
    u.export = exp.json()
    if os.environ.get("DUMP_EXPORT"):
        pathlib.Path(os.environ["DUMP_EXPORT"]).write_text(json.dumps(u.export, indent=1))
    assert_status(anon2.post("/_test/import", body=u.export, timeout=10), 204)
    u.log_after_import = len(mock.log())
    u.ada2 = Api(BASE, ada1.token)           # the token the client held before the upgrade
    return u


def test_the_stage_1_export_is_accepted_and_the_dossiers_appear(up):
    """S2-UP-1 S2-UP-2 (ids, states, researched_at, spent_units and the list survive; imported dossiers are listed)"""
    after = ok_json(up.ada2.get("/dossiers"))["dossiers"]
    key = lambda r: (r["dossier_id"], r["domain"], r["state"], r["researched_at"], r["spent_units"])
    assert sorted(map(key, after)) == sorted(map(key, up.list_before))
    assert [r["domain"] for r in after] == sorted(r["domain"] for r in after)
    for d in DOMS + [FAILED]:
        b = ok_json(up.ada2.get(f"/dossiers/{d}"))
        old = up.before[d]
        assert (b["dossier_id"], b["state"], b["researched_at"], b["spent_units"]) == \
               (old["dossier_id"], old["state"], old["researched_at"], old["spent_units"])
        if old["researched_at"]:
            assert parse_ts(b["researched_at"]) == parse_ts(old["researched_at"])


def test_sessions_accounts_and_retries_survive(up):
    """S2-UP-3 S2-UP-4 (token from before; password login; original response replayed for the same key and body)"""
    assert_status(up.ada2.get("/dossiers"), 200)
    assert_status(Api(BASE, up.bob1.token).get("/dossiers"), 200)
    assert_status(Api(BASE, up.zed["token"]).get("/dossiers"), 200)
    r = up.anon2.post("/auth/login", body={"email": "zed@example.com", "password": "zed-password-1"})
    assert ok_json(r)["user_id"] == up.zed["user_id"]
    err(up.anon2.post("/auth/login", body={"email": "zed@example.com", "password": "wrong password"}),
        401, "unauthenticated")
    for d in DOMS:
        r = up.ada2.post("/dossiers", body={"domain": d}, key=up.keys[d])
        assert ok_json(r, 200) == up.first[d]                    # the original 202 body
        err(up.ada2.post("/dossiers", body={"domain": "other-company.test"}, key=up.keys[d]),
            409, "idempotency_key_reuse")
    r = up.ada2.post("/dossiers/tidewell-pharma.test/refresh", key=up.refresh_key)
    assert ok_json(r, 200) == up.refreshed
    r = up.ada2.post("/dossiers", body={"domain": FAILED}, key=up.failed_key)
    assert ok_json(r, 200) == up.failed_first
    assert len(up.mock.log()) == up.log_after_import, "import and replays make no provider call (S2-UP-4)"


@pytest.mark.parametrize("domain", DOMS)
def test_every_imported_field_gains_the_candidates_the_export_can_support(up, domain):
    """S2-UP-5 S2-UP-6 S2-UP-7 S2-UP-8 (candidates: every exported citation, nothing the served text does not support,
    and every supported (page, value) of a page the export records; kind/published null or the page's; retrieved_at =
    researched_at; value/status/citations by the rule). The stage-1 export keeps only the selected citations, see RULINGS 55."""
    b = ok_json(up.ada2.get(f"/dossiers/{domain}"))
    old = up.before[domain]
    sup = served_support(domain, up.windows[domain])
    ra = parse_ts(b["researched_at"])
    comp = CORPUS_S2[domain]
    exported = json.dumps(up.export)
    for name in FIELDS:
        fld = b["fields"][name]
        m.check_field_consistency(name, fld, retrieved_at=ra)         # S2-UP-8: value/status/citations by the rule
        got = {(c["url"], c["value"]) for c in fld["candidates"]}
        assert got <= set(sup[name]), \
            f"{domain} {name}: candidates {sorted(got - set(sup[name]), key=str)} are not supported by any served text"
        for c in old["fields"][name]["citations"]:                     # what the stage-1 service recorded and cited
            assert (c["url"], old["fields"][name]["value"]) in got, f"{domain} {name}: exported citation {c['url']} lost"
            assert any(x["excerpt"] == c["excerpt"] and x["provider"] == c["provider"] and x["url"] == c["url"]
                       for x in fld["candidates"]), f"{domain} {name}: exported citation is not a candidate"
        recorded = {(u_, v) for (u_, v) in sup[name] if u_ in exported}
        assert recorded <= got, f"{domain} {name}: supported by a page the export records, yet no candidate: {sorted(recorded - got, key=str)}"
        for c in fld["candidates"]:
            assert parse_ts(c["retrieved_at"]) == ra, "S2-UP-7 retrieved_at is the dossier's researched_at"
            assert any(p == c["provider"] and o.collapse(c["excerpt"]) in o.collapse(s)
                       for p, s in sup[name][(c["url"], c["value"])]), \
                f"{name} {c['url']}: excerpt not copied from text that {c['provider']} served"
            assert o.supports(c["excerpt"], name, c["value"], domain)
            page = next(p for p in comp["pages"] if p["url"] == c["url"] and 0 in p["epochs"])
            assert c["kind"] is None or c["kind"] == m.kind_of(page, c["url"], domain)
            pub = m.page_published(page.get("published_at"))
            assert c["published_at"] is None or (pub and m.parse_rfc3339(c["published_at"]) == pub)
    assert any(f["candidates"] for f in b["fields"].values())


def test_a_dossier_that_never_completed_is_failed_and_unknown(up):
    """S2-UP-9 (a stage-1 dossier whose build failed has no candidates)"""
    b = ok_json(up.ada2.get(f"/dossiers/{FAILED}"))
    assert b["state"] == "failed" and b["researched_at"] is None
    assert all(f == UNKNOWN for f in b["fields"].values())


def test_the_next_build_replaces_the_imported_candidates(up):
    """S2-UP-10 (a refresh after the upgrade: candidates of that build, with kinds and times, at its time)"""
    d = "northwind-optics.test"
    old = ok_json(up.ada2.get(f"/dossiers/{d}"))
    assert_status(up.anon2.post("/_test/clock", body={"now": "2026-03-09T09:00:00+00:00"}), 204)
    mark = len(up.mock.log())
    assert_status(up.ada2.post(f"/dossiers/{d}/refresh", key=new_key()), 202)
    b = wait_state(up.ada2, d)
    assert b["state"] == "ready" and b["dossier_id"] == old["dossier_id"]
    assert b["spent_units"] > old["spent_units"]
    from conftest import check_build
    check_build(b, up.mock.log()[mark:])
    for fld in b["fields"].values():
        for c in fld["candidates"]:
            assert c["kind"] is not None and parse_ts(c["retrieved_at"]) == parse_ts("2026-03-09T09:00:00+00:00")
