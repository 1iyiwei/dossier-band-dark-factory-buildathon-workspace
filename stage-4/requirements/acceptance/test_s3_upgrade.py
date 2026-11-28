"""Stage 3 'Upgrades': a stage-3 service accepts the export of the team's stage-1 service (BASE_URL_S1) and of its
stage-2 service (BASE_URL_S2), both wired to the same mock. IDs (S3-UP-*) in ../LEDGER.md.

Stage-1 state goes into BASE_URL (a stage-3 instance), stage-2 state into BASE_URL_2. keystone-yards.test: epoch 0 is
what the old services build; epoch 1 (after the import) moves its headquarters and adds a CTO page."""
import json
from types import SimpleNamespace

import pytest

import oracle as o
import s2model as m
import s3model as s3
from conftest import (ADA, BASE, BASE2, BASE_S1, BASE_S2, FIELDS, MOCK, MOCK_TOKEN, NOW0, UNKNOWN, Api, Mock, PW,
                      assert_status, check_build, err, fixture, new_key, ok_json, parse_ts, CORPUS_S2, six)
from s3util import EIGHT, as_of, changes_all, dt, history_of, values

KY = "keystone-yards.test"
OTHER = "northwind-optics.test"
FAILED = "harbor-signal.test"
T0, T1, T2, T3 = ("2026-03-01T09:00:00+00:00", "2026-03-10T09:00:00+00:00", "2026-03-20T09:00:00+00:00",
                  "2026-04-01T09:00:00+00:00")
UTC_PUB = {"about": {0: "2026-01-20", 1: "2026-02-11"}, "leadership": {0: "2026-01-20", 1: "2026-01-20"},
           "team": {0: "2026-01-06", 1: "2026-01-06"}, "keystone-raise": {0: None, 1: None}}
EFFECTIVE = {"about": {0: "2026-01-15", 1: "2026-02-10"}}


def login(api, user=ADA):
    return Api(api.base, ok_json(api.post("/auth/login", body={"email": user["email"],
                                                               "password": user["password"]}))["token"])


def wait_state(api, d, timeout=40):
    import time
    t0 = time.time()
    while True:
        b = ok_json(api.get(f"/dossiers/{d}"))
        if b["state"] != "building":
            return b
        assert time.time() - t0 < timeout, "still building"
        time.sleep(0.2)


def allowed_true_from(url, epoch):
    """The date the page gives; with an Effective line either reading is accepted for an import: the stage-1/2
    export may not record the Effective line (RULINGS 66)."""
    key = url.rsplit("/", 1)[1]
    out = {UTC_PUB[key][epoch]}
    if key in EFFECTIVE:
        out.add(EFFECTIVE[key][epoch])
    return out


def six_view(f):
    """a field without the stage-3 additions, for comparison with what an older service returned"""
    return {k: v for k, v in f.items() if k not in ("true_from", "learned_at")}


@pytest.fixture(scope="module")
def s1():
    """A stage-1 service builds keystone (epoch 0) and a dossier that failed; its export is imported into BASE."""
    if not (BASE and BASE_S1 and MOCK):
        pytest.skip("BASE_URL, BASE_URL_S1 and MOCK_URL are needed (run.sh sets them)")
    mock = Mock(MOCK, MOCK_TOKEN)
    old, new = Api(BASE_S1), Api(BASE)
    fx = fixture(now=T0)
    assert_status(old.post("/_test/reset", body=fx, timeout=10), 204)
    assert_status(new.post("/_test/reset", body=fx, timeout=10), 204)
    mock.reset(0)
    ada1 = login(old)
    out = SimpleNamespace(mock=mock, old=old, new=new, ada1=ada1, keys={}, first={}, before={})
    for d in (KY, OTHER):
        out.keys[d] = new_key()
        out.first[d] = ok_json(ada1.post("/dossiers", body={"domain": d}, key=out.keys[d]), 202)
        wait_state(ada1, d)
    mock.break_all()
    out.first[FAILED] = ok_json(ada1.post("/dossiers", body={"domain": FAILED}, key=new_key()), 202)
    assert wait_state(ada1, FAILED)["state"] == "failed"
    mock.clear()
    for d in (KY, OTHER, FAILED):
        out.before[d] = ok_json(ada1.get(f"/dossiers/{d}"))
    out.export = ok_json(old.get("/_test/export", timeout=10))
    assert_status(new.post("/_test/import", body=out.export, timeout=10), 204)
    out.ada = Api(BASE, ada1.token)                  # the token held before the upgrade
    out.calls_after_import = len(mock.log())
    return out


@pytest.fixture(scope="module")
def s2():
    """A stage-2 service makes two ready builds (epochs 0 and 1) and one failed build of keystone."""
    if not (BASE2 and BASE_S2 and MOCK):
        pytest.skip("BASE_URL_2, BASE_URL_S2 and MOCK_URL are needed (run.sh sets them)")
    mock = Mock(MOCK, MOCK_TOKEN)
    old, new = Api(BASE_S2), Api(BASE2)
    fx = fixture(now=T0)
    assert_status(old.post("/_test/reset", body=fx, timeout=10), 204)
    assert_status(new.post("/_test/reset", body=fx, timeout=10), 204)
    mock.reset(0)
    ada1 = login(old)
    out = SimpleNamespace(mock=mock, old=old, new=new, ada1=ada1, snaps={}, key=new_key())
    out.first = ok_json(ada1.post("/dossiers", body={"domain": KY}, key=out.key), 202)
    out.snaps["a"] = wait_state(ada1, KY)
    assert_status(old.post("/_test/clock", body={"now": T1}), 204)
    mock.epoch(1)
    assert_status(ada1.post(f"/dossiers/{KY}/refresh", key=new_key()), 202)
    out.snaps["b"] = wait_state(ada1, KY)
    assert_status(old.post("/_test/clock", body={"now": T2}), 204)
    mock.break_all()
    assert_status(ada1.post(f"/dossiers/{KY}/refresh", key=new_key()), 202)
    out.snaps["c"] = wait_state(ada1, KY)
    mock.clear()
    assert out.snaps["a"]["state"] == out.snaps["b"]["state"] == "ready" and out.snaps["c"]["state"] == "failed"
    out.export = ok_json(old.get("/_test/export", timeout=10))
    assert_status(new.post("/_test/import", body=out.export, timeout=10), 204)
    out.ada = Api(BASE2, ada1.token)
    return out


# --------------------------------------------------------------------------- stage 1 -> stage 3
def test_a_stage_1_export_is_accepted_with_tokens_and_idempotent_responses(s1):
    """S3-UP-1 S3-UP-2 (dossiers with ids, states, researched_at, spent_units; existing tokens; completed idempotent
    responses; no provider call)"""
    for d in (KY, OTHER, FAILED):
        b = ok_json(s1.ada.get(f"/dossiers/{d}"))
        old = s1.before[d]
        assert (b["dossier_id"], b["state"], b["spent_units"]) == (old["dossier_id"], old["state"], old["spent_units"])
        assert (b["researched_at"] is None) == (old["researched_at"] is None)
        if old["researched_at"]:
            assert dt(b["researched_at"]) == dt(old["researched_at"])
    for d in (KY, OTHER):
        assert ok_json(s1.ada.post("/dossiers", body={"domain": d}, key=s1.keys[d]), 200) == s1.first[d]
    assert len(s1.mock.log()) == s1.calls_after_import


def test_stage_1_import_gives_one_initial_entry_per_field_with_a_value_and_no_feed(s1):
    """S3-UP-3 S3-UP-4 S3-UP-5 S3-UP-8 S3-UP-13 (initial entries with learned_at = researched_at; true_from null unless the
    export records the date; executives unknown with no entry; the feed starts empty)"""
    assert changes_all(s1.ada) == []
    for d in (KY, OTHER):
        b = ok_json(s1.ada.get(f"/dossiers/{d}"))
        h = history_of(s1.ada, d)
        assert list(h["fields"]) == list(EIGHT)
        ra = dt(b["researched_at"])
        for name in FIELDS:
            f, es = b["fields"][name], h["fields"][name]
            if f["value"] is None:
                assert es == [] and f == UNKNOWN, (d, name)
                continue
            assert len(es) == 1 and es[0]["type"] == "initial" and es[0]["value"] == f["value"], (d, name, es)
            assert dt(es[0]["learned_at"]) == ra and dt(f["learned_at"]) == ra
            assert es[0]["citations"] == f["citations"]
            assert es[0]["true_from"] == f["true_from"]
            assert f["true_from"] in (None, *[c["true_from"] for c in f["candidates"]]), (d, name)
            for c in f["candidates"]:
                assert dt(c["learned_at"]) == dt(c["retrieved_at"]) == ra, "imported candidates: learned_at = retrieved_at"
                if c["published_at"] is None and c["true_from"] is not None:
                    pass                                  # an Effective date recorded by the export is allowed
                if c["published_at"] is not None:
                    assert c["true_from"] in (None, dt(c["published_at"]).astimezone(__import__("datetime").timezone.utc).date().isoformat(),
                                              *[x for x in EFFECTIVE.get(c["url"].rsplit("/", 1)[1], {}).values()]), c
        assert h["fields"]["executives"] == [] and b["fields"]["executives"] == UNKNOWN, d
    failed = ok_json(s1.ada.get(f"/dossiers/{FAILED}"))
    assert failed["state"] == "failed" and failed["researched_at"] is None
    assert all(f == UNKNOWN for f in failed["fields"].values())
    assert all(es == [] for es in history_of(s1.ada, FAILED)["fields"].values())


def test_stage_1_import_counts_as_one_ready_build_at_researched_at(s1):
    """S3-UP-6 S3-UP-7 S3-UP-14 (as_of at or after researched_at returns the imported fields; an earlier as_of and any as_of
    of a dossier with a null researched_at are 404; values: each candidate's URL is one version)"""
    for d in (KY, OTHER):
        b = ok_json(s1.ada.get(f"/dossiers/{d}"))
        ra = b["researched_at"]
        at = ok_json(as_of(s1.ada, d, ra))
        assert at["state"] == "ready" and at["fields"] == b["fields"] and at["spent_units"] == b["spent_units"]
        assert ok_json(as_of(s1.ada, d, "2030-01-01T00:00:00+00:00"))["fields"] == b["fields"]
        err(as_of(s1.ada, d, "2026-02-28T23:59:59+00:00"), 404, "not_found")
        assert at["fields"]["executives"] == UNKNOWN
        # values at a date after every date any candidate has: the selected value of the imported state, when its
        # candidate's true_from is not null; a candidate with a null true_from holds from no date
        v = ok_json(values(s1.ada, d, "2099-01-01", ra))["fields"]
        for name in FIELDS:
            by_url = {}
            for c in b["fields"][name]["candidates"]:
                by_url.setdefault(c["url"], []).append(c)
            holding = [c for c in b["fields"][name]["candidates"] if c["true_from"] is not None]
            want = m.derive([dict(c, provider=c["provider"]) for c in holding])
            assert v[name]["value"] == want["value"], (d, name)
            assert v[name]["true_from"] == (want["order"][0]["true_from"] if want["order"] else None)
        assert ok_json(values(s1.ada, d, "2099-01-01", ra))["fields"]["executives"]["value"] is None
        err(values(s1.ada, d, "2099-01-01", "2026-02-28T23:59:59+00:00"), 404, "not_found")
    err(as_of(s1.ada, FAILED, "2030-01-01T00:00:00+00:00"), 404, "not_found")
    err(values(s1.ada, FAILED, "2026-01-01"), 404, "not_found")


def test_the_first_build_after_a_stage_1_import_compares_with_the_imported_values(s1):
    """S3-UP-5 S3-UP-8 S3-UP-15 (a refresh at epoch 1: hq_city changes, executives appear as a change, unchanged fields add
    nothing; imported builds stay answerable by as_of)"""
    imported = ok_json(s1.ada.get(f"/dossiers/{KY}"))
    assert_status(s1.new.post("/_test/clock", body={"now": T3}), 204)
    s1.mock.epoch(1)
    mark = len(s1.mock.log())
    assert_status(s1.ada.post(f"/dossiers/{KY}/refresh", key=new_key()), 202)
    b = wait_state(s1.ada, KY)
    assert b["state"] == "ready"
    check_build(b, s1.mock.log()[mark:], epoch=1)
    feed = changes_all(s1.ada)
    assert [(e["domain"], e["field"], e["type"]) for e in feed] == [(KY, "hq_city", "change"), (KY, "executives", "change")]
    assert feed[0]["from"] == "Gdansk" and feed[0]["to"] == "Rotterdam" and dt(feed[0]["learned_at"]) == dt(T3)
    assert feed[0]["true_from"] == "2026-02-10" and feed[1]["from"] is None
    assert feed[1]["to"] == [{"title": "cto", "name": "Per Lund"}]
    h = history_of(s1.ada, KY)["fields"]
    assert [e["type"] for e in h["hq_city"]] == ["initial", "change"] and [e["type"] for e in h["executives"]] == ["change"]
    assert [e["type"] for e in h["ceo"]] == ["initial"], "an unchanged selected value adds nothing"
    assert ok_json(as_of(s1.ada, KY, imported["researched_at"]))["fields"]["hq_city"]["value"] == "Gdansk"
    assert ok_json(as_of(s1.ada, KY, T3))["fields"]["hq_city"]["value"] == "Rotterdam"
    assert ok_json(as_of(s1.ada, KY, imported["researched_at"]))["fields"]["executives"] == UNKNOWN


# --------------------------------------------------------------------------- stage 2 -> stage 3
def test_a_stage_2_export_is_accepted_and_keeps_tokens(s2):
    """S3-UP-1 S3-UP-2 (ids, states, researched_at, spent_units; token and replay)"""
    b = ok_json(s2.ada.get(f"/dossiers/{KY}"))
    old = s2.snaps["c"]
    assert (b["dossier_id"], b["state"], b["spent_units"]) == (old["dossier_id"], "failed", old["spent_units"])
    assert dt(b["researched_at"]) == dt(old["researched_at"]) == dt(T1)
    assert ok_json(s2.ada.post("/dossiers", body={"domain": KY}, key=s2.key), 200) == s2.first
    assert changes_all(s2.ada) == []


def test_stage_2_import_keeps_the_dossier_as_a_ready_build_at_researched_at(s2):
    """S3-UP-16 S3-UP-17 S3-UP-18 (as_of at and after the dossier's researched_at returns what the stage-2 service had; spent_units
    is the dossier's total, the failed build's spending included. The team's final stage-2 export records only the current
    dossier, not each build (RULINGS 75): earlier builds are not demanded)"""
    a, b, c = (s2.snaps[k] for k in "abc")
    for ts in (T1, T2, "2030-01-01T00:00:00+00:00"):
        got = ok_json(as_of(s2.ada, KY, ts))
        assert got["state"] == "ready" and dt(got["researched_at"]) == dt(b["researched_at"]), ts
        assert got["spent_units"] == c["spent_units"], (ts, got["spent_units"], c["spent_units"])
        for name in FIELDS:
            g, w = got["fields"][name], b["fields"][name]
            assert (g["value"], g["status"], g["citations"]) == (w["value"], w["status"], w["citations"]), (ts, name)
            key = lambda x: (x["url"], x["value"], x["excerpt"], x["provider"], x["kind"], x["published_at"],
                             x["retrieved_at"], x["selected"])
            assert [key(x) for x in g["candidates"]] == [key(x) for x in w["candidates"]], (ts, name)
        assert got["fields"]["executives"] == UNKNOWN, "an export of a stage-2 service has no executives"
    err(as_of(s2.ada, KY, "2026-02-28T23:59:59+00:00"), 404, "not_found")


def test_stage_2_candidates_get_learned_at_and_true_from_as_if_this_service_made_the_builds(s2):
    """S3-UP-19 S3-UP-20 S3-UP-21 (imported candidates: learned_at = retrieved_at = the build's time; true_from follows from the
    page's Effective and Published lines: the Effective date or the date of Published, null when neither is recorded)"""
    got = ok_json(as_of(s2.ada, KY, T1))
    n = 0
    for name in FIELDS:
        for c in got["fields"][name]["candidates"]:
            n += 1
            assert dt(c["learned_at"]) == dt(c["retrieved_at"]) == dt(T1), (name, c)
            assert c["true_from"] in allowed_true_from(c["url"], 1) or \
                (c["true_from"] is None and UTC_PUB[c["url"].rsplit("/", 1)[1]][1] is None), (name, c)
    assert n >= 6
    hq = got["fields"]["hq_city"]["candidates"][0]
    assert hq["value"] == "Rotterdam" and dt(hq["learned_at"]) == dt(T1)


def test_stage_2_history_is_one_initial_entry_per_field_with_a_value(s2):
    """S3-UP-3 S3-UP-4 S3-UP-8 S3-UP-22 (learned_at the dossier's researched_at; no executives entry; the feed is empty;
    an as_of response takes each field's learned_at and true_from from that history)"""
    cur = ok_json(s2.ada.get(f"/dossiers/{KY}"))
    h = history_of(s2.ada, KY)["fields"]
    for name in FIELDS:
        f = cur["fields"][name]
        if f["value"] is None:
            assert h[name] == []
            continue
        assert len(h[name]) == 1 and h[name][0]["type"] == "initial" and h[name][0]["value"] == f["value"]
        assert dt(h[name][0]["learned_at"]) == dt(T1) and h[name][0]["citations"] == f["citations"]
    assert h["executives"] == []
    assert changes_all(s2.ada) == []
    got = ok_json(as_of(s2.ada, KY, T1))["fields"]
    for name in FIELDS:
        if h[name]:
            assert (got[name]["learned_at"] is not None and dt(got[name]["learned_at"]) == dt(h[name][0]["learned_at"])
                    and got[name]["true_from"] == h[name][0]["true_from"]), name


def test_stage_2_import_gives_values_by_its_one_version_per_url(s2):
    """S3-UP-23 (values at as_of = researched_at: each imported candidate's URL is one version holding from its true_from;
    nothing holds before it; executives unknown)"""
    cur = ok_json(as_of(s2.ada, KY, T1))["fields"]
    for ta in ("2026-01-10", "2026-01-25", "2026-02-15", "2099-01-01"):
        v = ok_json(values(s2.ada, KY, ta, T1))["fields"]
        for name in FIELDS:
            holding = [c for c in cur[name]["candidates"] if c["true_from"] is not None and c["true_from"] <= ta]
            want = m.derive(holding)
            assert v[name]["value"] == want["value"], (ta, name, v[name]["value"], want["value"])
            assert v[name]["true_from"] == (want["order"][0]["true_from"] if want["order"] else None)
        assert v["executives"]["value"] is None
    assert ok_json(values(s2.ada, KY, "2099-01-01", T1))["fields"]["hq_city"]["value"] in ("Rotterdam", None)
    err(values(s2.ada, KY, "2026-01-25", "2026-02-28T23:59:59+00:00"), 404, "not_found")


def test_the_first_build_after_a_stage_2_import_adds_executives_as_a_change(s2):
    """S3-UP-5 S3-UP-8 S3-UP-15 (epoch 1 again: same selected values for the six fields: no entry; executives get a
    value: a change, not an initial entry; imported builds stay answerable)"""
    assert_status(s2.new.post("/_test/clock", body={"now": T3}), 204)
    s2.mock.epoch(1)
    mark = len(s2.mock.log())
    assert_status(s2.ada.post(f"/dossiers/{KY}/refresh", key=new_key()), 202)
    b = wait_state(s2.ada, KY)
    assert b["state"] == "ready"
    check_build(b, s2.mock.log()[mark:], epoch=1)
    feed = changes_all(s2.ada)
    assert [(e["field"], e["type"]) for e in feed] == [("executives", "change")], feed
    assert feed[0]["from"] is None and feed[0]["to"] == [{"title": "cto", "name": "Per Lund"}]
    h = history_of(s2.ada, KY)["fields"]
    assert [e["type"] for e in h["executives"]] == ["change"] and all(
        [e["type"] for e in h[f]] == ["initial"] for f in FIELDS if h[f])
    assert ok_json(as_of(s2.ada, KY, T1))["fields"]["executives"] == UNKNOWN
    assert ok_json(as_of(s2.ada, KY, T3))["fields"]["executives"]["value"] == [{"title": "cto", "name": "Per Lund"}]


def test_state_a_stage_2_service_imported_from_stage_1_counts_as_one_ready_build(s1, s2):
    """S3-UP-24 (stage-1 export -> stage-2 service -> its export -> stage-3: one build that completed ready at the dossier's
    researched_at; an earlier as_of is 404; executives unknown; history one initial entry per field with a value)"""
    mid, dst = Api(BASE_S2), Api(BASE2)
    assert_status(mid.post("/_test/import", body=s1.export, timeout=10), 204)       # replaces the stage-2 state
    chain = ok_json(mid.get("/_test/export", timeout=10))
    assert_status(dst.post("/_test/import", body=chain, timeout=10), 204)
    api = Api(BASE2, s1.ada.token)
    for d in (KY, OTHER):
        b = ok_json(api.get(f"/dossiers/{d}"))
        ra = b["researched_at"]
        assert dt(ra) == dt(s1.before[d]["researched_at"])
        at = ok_json(as_of(api, d, ra))
        assert at["fields"]["executives"] == UNKNOWN and at["spent_units"] == b["spent_units"]
        for name in FIELDS:
            assert at["fields"][name]["value"] == b["fields"][name]["value"]
        err(as_of(api, d, "2026-02-28T23:59:59+00:00"), 404, "not_found")
        h = history_of(api, d)["fields"]
        assert h["executives"] == [] and all(len(h[f]) == (1 if b["fields"][f]["value"] is not None else 0) for f in FIELDS)
    assert changes_all(api) == []
