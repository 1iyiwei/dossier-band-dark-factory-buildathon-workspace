"""Stage 4 'Upgrades': a stage-4 service accepts the export of the team's stage-1, stage-2 and stage-3 services
(BASE_URL_S1/S2/S3, wired to the same mock). IDs (S4-UP-*) in ../LEDGER.md.
Stage-3 state goes into BASE (a stage-4 instance); stage-1 and stage-2 state into BASE_2."""
import json
from types import SimpleNamespace

import pytest

import s2model as m
import s3model as s3
from conftest import (ADA, BASE, BASE2, BASE_S1, BASE_S2, BASE_S3, FIELDS, MOCK, MOCK_TOKEN, UNKNOWN, Api, Mock, assert_status,
                      check_build, fixture, new_key, ok_json)
from s3util import as_of, changes_all, dt, history_of, values
from s4util import EIGHT, P, PT, V, check_keys, since_of
from test_s3_upgrade import login, wait_state

KY = "keystone-yards.test"


def old_builds(api, domain, times):
    """The model builds of what an older service answers by `as_of` at each time (candidates as it recorded them;
    an imported candidate without origin takes the host of its URL)."""
    out = []
    for ts in times:
        j = ok_json(as_of(api, domain, ts))
        by = {}
        for name, f in j["fields"].items():
            for c in f["candidates"]:
                x = dict(c, origin=m.host_of(c["url"]))
                by.setdefault(c.get("title", name), []).append(x)
        out.append(s3.Build(dt(j["researched_at"]), {"https://x.test/all": (None, by)}))
    return out


@pytest.fixture(scope="module")
def s3src():
    """A stage-3 service builds prism-harbor (epochs 0, 1) and a dossier whose only build failed; imported into BASE."""
    if not (BASE and BASE_S3 and MOCK):
        pytest.skip("BASE_URL, BASE_URL_S3 and MOCK_URL are needed (run.sh sets them)")
    mock = Mock(MOCK, MOCK_TOKEN)
    old, new = Api(BASE_S3), Api(BASE)
    fx = fixture(now=PT["0"])
    assert_status(old.post("/_test/reset", body=fx, timeout=10), 204)
    assert_status(new.post("/_test/reset", body=fx, timeout=10), 204)
    mock.reset(0)
    ada1 = login(old)
    out = SimpleNamespace(mock=mock, old=old, new=new, ada1=ada1, key=new_key(), failkey=new_key())
    out.first = ok_json(ada1.post("/dossiers", body={"domain": P}, key=out.key), 202)
    wait_state(ada1, P)
    assert_status(old.post("/_test/clock", body={"now": PT["1"]}), 204)
    mock.epoch(1)
    assert_status(ada1.post(f"/dossiers/{P}/refresh", key=new_key()), 202)
    wait_state(ada1, P)
    mock.break_all()
    out.failfirst = ok_json(ada1.post("/dossiers", body={"domain": V}, key=out.failkey), 202)
    assert wait_state(ada1, V)["state"] == "failed"
    mock.clear()
    out.times = [PT["0"], PT["1"]]
    out.old_get = ok_json(ada1.get(f"/dossiers/{P}"))
    out.old_hist = history_of(ada1, P)
    out.old_feed = changes_all(ada1)
    out.old_asof = [ok_json(as_of(ada1, P, t)) for t in out.times]
    out.builds = old_builds(ada1, P, out.times)
    out.corro = s3.corroboration(out.builds)
    out.export = ok_json(old.get("/_test/export", timeout=10))
    assert_status(new.post("/_test/import", body=out.export, timeout=10), 204)
    out.ada = Api(BASE, ada1.token)
    out.calls = len(mock.log())
    return out


def test_a_stage_3_export_keeps_dossiers_candidates_history_feed_and_idempotent_responses(s3src):
    """S4-UP-1 S4-UP-3 (dossiers, candidates, history, the feed with its seq, completed idempotent responses, tokens; the
    import makes no provider call; the six fields and executives answer as the stage-3 service did)"""
    s = s3src
    got = ok_json(s.ada.get(f"/dossiers/{P}"))
    for name in FIELDS + ("executives",):
        g, o_ = got["fields"][name], s.old_get["fields"][name]
        for k in ("value", "status", "true_from", "learned_at", "citations"):
            assert g[k] == o_[k], (name, k)
        key = lambda c: (c["url"], c["value"], c.get("title"), c["excerpt"], c["provider"], c["kind"], c["published_at"],
                         c["retrieved_at"], c["selected"], c["true_from"], c["learned_at"])
        assert [key(c) for c in g["candidates"]] == [key(c) for c in o_["candidates"]], name
    assert (got["dossier_id"], got["researched_at"], got["spent_units"]) == (
        s.old_get["dossier_id"], s.old_get["researched_at"], s.old_get["spent_units"])
    h = history_of(s.ada, P)
    for name in s.old_hist["fields"]:
        assert h["fields"][name] == s.old_hist["fields"][name], name
    assert changes_all(s.ada) == s.old_feed
    assert ok_json(s.ada.post("/dossiers", body={"domain": P}, key=s.key), 200) == s.first
    assert ok_json(s.ada.post("/dossiers", body={"domain": V}, key=s.failkey), 200) == s.failfirst
    assert len(s.mock.log()) == s.calls


def test_imported_candidates_have_the_host_of_their_url_as_origin_and_investors_is_unknown(s3src):
    """S4-UP-4 S4-UP-5 S4-OR-9 S4-FK-6 (every imported candidate: origin = its URL's host, normalised; `investors` unknown in the
    state and in every build kept, with no history entry; the keys of every field follow from the imported builds, each
    gathered at its build's time)"""
    s = s3src
    got = ok_json(s.ada.get(f"/dossiers/{P}"))
    assert list(got["fields"]) == list(EIGHT)
    assert got["fields"]["investors"] == UNKNOWN
    for name, f in got["fields"].items():
        for c in f["candidates"]:
            assert c["origin"] == m.host_of(c["url"]), (name, c["url"], c["origin"])
    check_keys(got["fields"], s.corro[-1], "imported GET")
    for k, t in enumerate(s.times):
        at = ok_json(as_of(s.ada, P, t))
        assert list(at["fields"]) == list(EIGHT) and at["fields"]["investors"] == UNKNOWN
        check_keys(at["fields"], s.corro[k], f"as_of {k}")
    h = history_of(s.ada, P)
    assert list(h["fields"]) == list(EIGHT) and h["fields"]["investors"] == []
    v = ok_json(values(s.ada, P, "2026-01-01", s.times[1]))["fields"]
    assert list(v) == list(EIGHT) and v["investors"]["value"] is None and v["investors"]["citations"] == []
    ceo = got["fields"]["ceo"]
    assert ceo["corroborated"] is True and dt(ceo["corroborated_since"]) == dt(PT["1"]), "own page + registry in build 1"


def test_a_dossier_whose_import_has_no_ready_build_gets_initial_for_investors_later(s3src):
    """S4-UP-6 (failed on the stage-3 service: every field unknown; its first ready build after the import adds an `initial`
    entry for investors, as for every other field with a value)"""
    s = s3src
    b = ok_json(s.ada.get(f"/dossiers/{V}"))
    assert b["state"] == "failed" and b["researched_at"] is None and all(f == UNKNOWN for f in b["fields"].values())
    assert_status(s.new.post("/_test/clock", body={"now": "2026-09-01T09:00:00+00:00"}), 204)
    s.mock.epoch(0)
    mark = len(s.mock.log())
    assert_status(s.ada.post(f"/dossiers/{V}/refresh", key=new_key()), 202)
    b = wait_state(s.ada, V)
    assert b["state"] == "ready"
    check_build(b, s.mock.log()[mark:])
    h = history_of(s.ada, V)["fields"]
    assert [e["type"] for e in h["investors"]] == ["initial"] and h["investors"][0]["value"] == b["fields"]["investors"]["value"]
    assert all(e["type"] == "initial" for f in h.values() for e in f)
    assert all(e["field"] != "investors" for e in changes_all(s.ada) if e["domain"] == V)


def test_the_first_build_after_a_stage_3_import_adds_investors_as_a_change(s3src):
    """S4-UP-6 S4-INV-12 (prism-harbor already had a ready build: the investors the new build finds are a `change` from null,
    in the history and the feed; other unchanged fields add nothing; the imported builds stay answerable)"""
    s = s3src
    assert_status(s.new.post("/_test/clock", body={"now": "2026-09-05T09:00:00+00:00"}), 204)
    s.mock.epoch(1)
    mark = len(s.mock.log())
    assert_status(s.ada.post(f"/dossiers/{P}/refresh", key=new_key()), 202)
    b = wait_state(s.ada, P)
    assert b["state"] == "ready"
    check_build(b, s.mock.log()[mark:], epoch=1)
    assert b["fields"]["investors"]["value"] == ["Northwind Ventures"]
    h = history_of(s.ada, P)["fields"]["investors"]
    assert [e["type"] for e in h] == ["change"] and h[0]["true_from"] == "2024-05-02"
    new_feed = changes_all(s.ada)[len(s.old_feed):]
    assert [(e["domain"], e["field"], e["type"], e["from"], e["to"]) for e in new_feed] == [
        (P, "investors", "change", None, ["Northwind Ventures"])]
    for k, t in enumerate(s.times):
        at = ok_json(as_of(s.ada, P, t))
        assert at["fields"]["investors"] == UNKNOWN
        check_keys(at["fields"], s.corro[k], f"as_of {k} after a later build")


# --------------------------------------------------------------------------- stage 1 and stage 2 exports
def _older(base_old, base_new):
    if not (base_old and base_new and MOCK):
        pytest.skip("the older service and a second stage-4 instance are needed (run.sh sets them)")
    mock = Mock(MOCK, MOCK_TOKEN)
    old, new = Api(base_old), Api(base_new)
    fx = fixture(now=PT["0"])
    assert_status(old.post("/_test/reset", body=fx, timeout=10), 204)
    assert_status(new.post("/_test/reset", body=fx, timeout=10), 204)
    mock.reset(0)
    ada1 = login(old)
    assert_status(ada1.post("/dossiers", body={"domain": KY}, key=new_key()), 202)
    old_b = wait_state(ada1, KY)
    snap = ok_json(old.get("/_test/export", timeout=10))
    assert_status(new.post("/_test/import", body=snap, timeout=10), 204)
    return Api(base_new, ada1.token), old_b


@pytest.mark.parametrize("which", ["s1", "s2"])
def test_stage_1_and_stage_2_exports_get_origins_by_host_and_unknown_investors(which):
    """S4-UP-1 S4-UP-4 S4-UP-5 S4-FK-6 (imported candidates: origin = host of the URL; the imported state counts as one build
    gathered at researched_at: a field with two hosts behind its value is corroborated since then; investors unknown
    with no history entry)"""
    api, old_b = _older(BASE_S1 if which == "s1" else BASE_S2, BASE2)
    b = ok_json(api.get(f"/dossiers/{KY}"))
    assert list(b["fields"]) == list(EIGHT) and b["fields"]["investors"] == UNKNOWN and b["fields"]["executives"] == UNKNOWN
    assert b["state"] == "ready" and dt(b["researched_at"]) == dt(old_b["researched_at"])
    by = {}
    for name in FIELDS:
        f = b["fields"][name]
        assert f["value"] == old_b["fields"][name]["value"], name
        by[name] = [dict(c, origin=m.host_of(c["url"])) for c in f["candidates"]]
        for c in f["candidates"]:
            assert c["origin"] == m.host_of(c["url"]), (name, c["url"], c["origin"])
    row = s3.corroboration([s3.Build(dt(b["researched_at"]), {"https://x.test/all": (None, by)})])[0]
    check_keys(b["fields"], row, which)
    assert history_of(api, KY)["fields"]["investors"] == []
    at = ok_json(as_of(api, KY, b["researched_at"]))
    assert at["fields"] == b["fields"]
