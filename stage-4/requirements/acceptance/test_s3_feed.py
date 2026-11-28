"""Stage 3: the change feed across dossiers, and concurrency (stage-3.md Operations 4, Concurrency).
IDs (S3-*) in docstrings refer to ../LEDGER.md. Companies fleet-*.test change their CEO between epoch 0 and 1."""
import threading
import time

import pytest

import s2model as m
import s3model as s3
from conftest import (BASE, CORPUS_S2, FIELDS, MOCK, MOCK_TOKEN, Api, Mock, World, assert_status, domain_searches,
                      fixture, new_key, ok_json, pmap)
from s3util import as_of, changes_all, dt, history_of, values

FLEET = [f"fleet-{n}.test" for n in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")]
T0, T1 = "2026-03-01T09:00:00+00:00", "2026-03-20T09:00:00+00:00"


@pytest.fixture
def fleet(pworld):
    """Six dossiers built at epoch 0, the web then moves to epoch 1 (every CEO changes)."""
    w = pworld
    w.mock.epoch(0)
    for d in FLEET:
        assert_status(w.request(w.ada, d), 202)
    for d in FLEET:
        assert w.wait(w.ada, d, 40)["state"] == "ready"
    assert changes_all(w.ada) == [], "initial builds publish no feed entry"
    assert_status(w.clock(T1), 204)
    w.mock.epoch(1)
    return w


def new_ceos(d):
    res, info, _ = s3.expected_all(d, 1, CORPUS_S2)
    (url, val), = res["ceo"]["must"]
    return val


def test_concurrent_refreshes_of_one_dossier_run_one_build_and_add_each_entry_once(fleet):
    """S3-OP-4 S3-CC-1 S3-FD-11 S3-HI-14 (30 simultaneous refreshes of one dossier: one build; its change appears once in
    the history and once in the feed; the build's time is the clock's)"""
    w = fleet
    d = FLEET[0]
    before = ok_json(w.ada.get(f"/dossiers/{d}"))
    mark = len(w.mock.log())
    rs = pmap(lambda _: w.ada.post(f"/dossiers/{d}/refresh", key=new_key()), range(30))
    assert all(r.status_code == 202 for r in rs), [r.status_code for r in rs]
    after = w.wait(w.ada, d, 40)
    assert after["state"] == "ready" and after["fields"]["ceo"]["value"] == new_ceos(d)
    log = w.mock.log()[mark:]
    assert len(domain_searches(log, d)) == 1, "one build ran"
    feed = [e for e in changes_all(w.ada) if e["domain"] == d]
    assert [(e["field"], e["to"]) for e in feed] == [("ceo", new_ceos(d))]
    assert feed[0]["from"] == before["fields"]["ceo"]["value"]
    h = history_of(w.ada, d)["fields"]["ceo"]
    assert len(h) == 2 and h[0]["type"] == "initial" and h[1]["value"] == new_ceos(d)
    # the first tf 2024-01-01, the new one 2026-03-01 is later: a change
    assert feed[0]["type"] == "change" and feed[0]["true_from"] == "2026-03-01"
    assert dt(feed[0]["learned_at"]) == dt(T1)


def test_concurrent_refreshes_of_many_dossiers_with_concurrent_reads(fleet):
    """S3-CC-1 S3-CC-2 S3-FD-3 S3-FD-11 (6 dossiers x 8 refreshes while readers hit GET, as_of, values, history and
    /changes: same results as one at a time in some order: every change once, none missing, seq unique and increasing
    in the order of the entries, no 5xx)"""
    w = fleet
    stop = threading.Event()
    seen_feeds, errors = [], []

    def reader(i):
        api = Api(BASE, w.ada.token)
        while not stop.is_set():
            try:
                d = FLEET[i % 6]
                for path, params in ((f"/dossiers/{d}", None), (f"/dossiers/{d}/history", None),
                                     (f"/dossiers/{d}", {"as_of": T0}), (f"/dossiers/{d}/values", {"true_at": "2026-03-10"}),
                                     ("/changes", {"limit": 200})):
                    r = api.get(path, params=params)
                    assert r.status_code == 200, (path, r.status_code, r.text[:200])
                    if path == "/changes":
                        seen_feeds.append(r.json()["changes"])
            except AssertionError as e:                                # includes 5xx
                errors.append(str(e))
                return

    readers = [threading.Thread(target=reader, args=(i,)) for i in range(6)]
    for th in readers:
        th.start()
    jobs = [d for d in FLEET for _ in range(8)]
    rs = pmap(lambda d: w.ada.post(f"/dossiers/{d}/refresh", key=new_key()), jobs)
    assert all(r.status_code == 202 for r in rs)
    for d in FLEET:
        assert w.wait(w.ada, d, 60)["state"] == "ready"
    stop.set()
    for th in readers:
        th.join(10)
    assert not errors, errors[:3]
    feed = changes_all(w.ada)
    assert sorted(e["domain"] for e in feed) == sorted(FLEET), "one entry per dossier, none twice, none missing"
    assert all(e["field"] == "ceo" and e["to"] == new_ceos(e["domain"]) for e in feed)
    seqs = [e["seq"] for e in feed]
    assert seqs == sorted(seqs) and len(set(seqs)) == 6 and all(s > 0 for s in seqs)
    for d in FLEET:
        assert len(domain_searches([c for c in w.mock.log()], d)) == 2, f"{d}: first build + exactly one refresh build"
        assert len(history_of(w.ada, d)["fields"]["ceo"]) == 2
    # every feed page a reader saw is a prefix of the final feed (the feed only grows, in seq order)
    final = {e["seq"]: e for e in feed}
    for page in seen_feeds:
        for e in page:
            assert final[e["seq"]] == e
        assert [e["seq"] for e in page] == sorted(e["seq"] for e in page)


def test_a_failed_refresh_and_a_no_change_refresh_add_nothing_and_later_entries_have_larger_seq(fleet):
    """S3-HI-11 S3-HI-6 S3-FD-3 (failed build: no entry; a build with the same selected values: no entry; a later change
    gets a larger seq than every earlier entry)"""
    w = fleet
    d1, d2 = FLEET[0], FLEET[1]
    w.mock.break_all()
    w.refresh(w.ada, d1)
    w.mock.clear()
    assert changes_all(w.ada) == []
    w.refresh(w.ada, d1)                                        # epoch 1: ceo changes
    first = changes_all(w.ada)
    assert [e["domain"] for e in first] == [d1]
    w.refresh(w.ada, d1)                                        # same web again: nothing new
    assert changes_all(w.ada) == first
    assert_status(w.clock("2026-03-25T09:00:00+00:00"), 204)
    w.refresh(w.ada, d2)
    both = changes_all(w.ada)
    assert [e["domain"] for e in both] == [d1, d2] and both[1]["seq"] > both[0]["seq"]
    assert dt(both[1]["learned_at"]) == dt("2026-03-25T09:00:00+00:00")
    assert both[0] == first[0], "an entry never changes"
    # a refresh of d1 back at epoch 0 is a change again (a new entry), seq larger
    w.mock.epoch(0)
    w.refresh(w.ada, d1)
    third = changes_all(w.ada)
    assert len(third) == 3 and third[2]["domain"] == d1 and third[2]["seq"] > both[1]["seq"]
    assert third[2]["to"] != first[0]["to"] and third[2]["from"] == first[0]["to"]


def test_the_feed_is_shared_by_every_user(fleet):
    """S3-FD-12 (every authenticated user reads the same feed, history and values as with GET /dossiers)"""
    w = fleet
    w.refresh(w.ada, FLEET[2])
    a = changes_all(w.ada)
    b = changes_all(w.bob)
    assert a == b and len(a) == 1
    assert history_of(w.ada, FLEET[2]) == history_of(w.bob, FLEET[2])
