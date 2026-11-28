"""Shared drivers for the stage-4 tests: the prism-harbor timeline (six epochs of the mock web, a failed build between
epochs 1 and 2), corroboration expectations from s3model.py (stage-4.md alone), response helpers."""
from __future__ import annotations

from types import SimpleNamespace

import s2model as m
import s3model as s3
from conftest import CORPUS_S2, MOCK, MOCK_TOKEN, Mock, World, assert_status, check_build, fixture, ok_json
from s3util import dt, run_timeline

P = "prism-harbor.test"
PT = {"0": "2026-03-01T09:00:00+00:00", "1": "2026-04-01T09:00:00+00:00", "f": "2026-04-15T09:00:00+00:00",
      "2": "2026-05-01T09:00:00+00:00", "3": "2026-06-01T09:00:00+00:00", "4": "2026-07-01T09:00:00+00:00",
      "5": "2026-08-01T09:00:00+00:00"}
PSTEPS = [("0", 0, False), ("1", 1, False), ("f", 1, True), ("2", 2, False), ("3", 3, False), ("4", 4, False),
          ("5", 5, False)]
EIGHT = s3.ALL
V = "vantage-mill.test"


def prism_timeline():
    tl = run_timeline(domain=P, steps=PSTEPS, times=PT)
    tl.corro = s3.corroboration(tl.builds)
    return tl


def since_of(fld):
    s = fld["corroborated_since"]
    return None if s is None else dt(s)


def check_keys(fields, row, who=""):
    """origins / corroborated / corroborated_since of all eight fields against a corroboration row of the model"""
    for f in EIGHT:
        r, got = row[f], fields[f]
        assert got["origins"] == r["origins"], f"{who} {f}: origins {got['origins']} != {r['origins']}"
        assert got["corroborated"] is r["corroborated"], f"{who} {f}: corroborated {got['corroborated']} != {r['corroborated']}"
        assert since_of(got) == r["since"], \
            f"{who} {f}: corroborated_since {got['corroborated_since']} != {r['since']}"


def single_build(domain, epoch=0, time=None):
    """One build of `domain` on a clean service (read-only afterwards): (world, body, calls, model build)."""
    mock = Mock(MOCK, MOCK_TOKEN)
    w = World(mock)
    w.reset(fixture(now=time or "2026-03-01T09:00:00+00:00"))
    mock.epoch(epoch)
    body, calls = w.build(w.ada, domain)
    return SimpleNamespace(w=w, mock=mock, body=body, calls=calls, epoch=epoch,
                           model=s3.build_from_epoch(domain, epoch, dt(time or "2026-03-01T09:00:00+00:00"), CORPUS_S2))
