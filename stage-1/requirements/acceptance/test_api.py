"""Domains, dossier endpoints and list. Ledger IDs in each docstring."""
import time
import urllib.parse

import pytest

from conftest import (Api, BASE, assert_status, check_shape, err, new_key, ok_json, parse_ts,
                      pmap, EXPECT)

L63 = "a" * 63
LONGEST = ".".join([L63, L63, L63, "b" * 61])          # 63*3 + 61 + 3 dots = 253
assert len(LONGEST) == 253


@pytest.mark.parametrize("raw,norm", [
    ("Acme-Robotics.TEST.", "acme-robotics.test"),
    ("www.acme-robotics.test", "acme-robotics.test"),
    ("  WWW.Acme-Robotics.Test  ", "acme-robotics.test"),
    ("\tacme-robotics.test\n", "acme-robotics.test"),
    ("www.www.acme.test", "www.acme.test"),
    ("WWW.ACME.TEST.", "acme.test"),
    ("a.b", "a.b"), ("x-1.y2.test", "x-1.y2.test"), (L63 + ".test", L63 + ".test"),
    (LONGEST, LONGEST), ("1.2", "1.2"), ("a--b.test", "a--b.test"),
])
def test_normalisation_in_body(world, raw, norm):
    """DM-1 DM-4 PD-1"""
    r = world.request(world.ada, raw)
    j = ok_json(r, 202)
    assert j["domain"] == norm and j["state"] == "building" and isinstance(j["dossier_id"], str)
    assert len(j["dossier_id"]) <= 64
    assert world.dossier(world.ada, norm)["domain"] == norm


@pytest.mark.parametrize("raw", [
    "", " ", "localhost", "acme_co.test", "-a.test", "a-.test", "a.-b.test", "a..test", ".test",
    "acme.test..", "www.", "www.test", "www.acme", "https://acme.test", "http://acme.test/",
    "acme.test/about", "acme.test:8080", "user@acme.test", "ac me.test", "münchen.test",
    "a." + "d" * 64, "x" * 64 + ".test", LONGEST + "c",
    ".".join(["a" * 63] * 4 + ["bb"]), "acme.test?x=1", "acme.test#f", "a.te$t", "*.acme.test",
])
def test_invalid_domains_in_body(world, raw):
    """DM-2"""
    err(world.request(world.ada, raw), 422, "validation_failed")
    assert ok_json(world.ada.get("/dossiers")) == {"dossiers": [], "has_more": False}


def test_domain_missing_or_wrong_type(world):
    """PD-3 PD-4"""
    k = new_key
    err(world.ada.post("/dossiers", body={}, key=k()), 422, "validation_failed")
    err(world.ada.post("/dossiers", body={"Domain": "a.test"}, key=k()), 422, "validation_failed")
    for bad in (5, ["a.test"], {"domain": "a.test"}, True, None):
        err(world.ada.post("/dossiers", body={"domain": bad}, key=k()), 400, "malformed_request")
    err(world.ada.post("/dossiers", raw=b"{nope", key=k()), 400, "malformed_request")
    err(world.ada.post("/dossiers", raw=b"", key=k()), 400, "malformed_request")
    err(world.ada.post("/dossiers", raw=b"[]", key=k()), 400, "malformed_request")


def test_unknown_body_fields_ignored(world):
    """CV-2"""
    j = ok_json(world.ada.post("/dossiers", body={"domain": "extra.test", "foo": [1], "x": None},
                               key=new_key()), 202)
    assert j["domain"] == "extra.test"


@pytest.mark.parametrize("spelling", ["{D}", "www.{d}", "{d}.", "WWW.{D}.", " {d} "])
def test_every_spelling_names_one_dossier(world, spelling):
    """DM-3 GD-7 PD-2"""
    first = ok_json(world.request(world.ada, "spell-one.test"), 202)
    again = ok_json(world.request(world.bob, spelling.format(d="spell-one.test",
                                                              D="Spell-One.TEST")), 200)
    assert again["dossier_id"] == first["dossier_id"] and again["domain"] == "spell-one.test"
    path = urllib.parse.quote(spelling.format(d="spell-one.test", D="Spell-One.TEST"), safe="")
    got = ok_json(world.bob.get(f"/dossiers/{path}"))
    assert got["dossier_id"] == first["dossier_id"] and got["domain"] == "spell-one.test"
    assert len(ok_json(world.ada.get("/dossiers"))["dossiers"]) == 1


@pytest.mark.parametrize("seg", ["localhost", "acme_co.test", "-a.test", "www.test", "x..test",
                                 "https%3A%2F%2Facme.test", "acme.test%3A80", "a%20b.test"])
def test_invalid_domain_in_path_is_422(world, seg):
    """DM-5"""
    err(world.ada.get(f"/dossiers/{seg}"), 422, "validation_failed")
    err(world.ada.post(f"/dossiers/{seg}/refresh", key=new_key()), 422, "validation_failed")


def test_unknown_dossier_404(world):
    """GD-7 RF-3"""
    err(world.ada.get("/dossiers/nothere.test"), 404, "not_found")
    err(world.ada.post("/dossiers/nothere.test/refresh", key=new_key()), 404, "not_found")
    err(world.ada.post("/dossiers/WWW.NotHere.test./refresh", key=new_key()), 404, "not_found")


def test_new_dossier_before_first_ready(pworld):
    """GD-1 GD-2 GD-3 PD-1 CV-5 CV-4 BD-7"""
    w = pworld
    w.mock.fault("nimble", ["search", "extract", "research"], "delay", 2)
    w.mock.fault("tavily", ["search", "extract"], "delay", 2)
    t0 = time.time()
    j = ok_json(w.request(w.ada, "northwind-optics.test"), 202)
    assert time.time() - t0 < 2.0, "POST must not wait for the build"
    assert set(j) >= {"dossier_id", "domain", "state"} and j["state"] == "building"
    b = w.dossier(w.ada, "northwind-optics.test")
    check_shape(b)
    assert b["state"] == "building" and b["researched_at"] is None
    assert all(f["status"] == "unknown" and f["value"] is None and f["citations"] == []
               for f in b["fields"].values())
    assert b["dossier_id"] == j["dossier_id"]
    listed = ok_json(w.ada.get("/dossiers"))["dossiers"][0]
    assert listed["state"] == "building" and listed["legal_name"] is None
    assert listed["researched_at"] is None
    w.wait(w.ada, "northwind-optics.test", timeout=60)


def test_every_user_sees_the_same_dossiers(pworld):
    """GD-8"""
    w = pworld
    body, _ = w.build(w.ada, "tidewell-pharma.test")
    other = ok_json(w.bob.get("/dossiers/tidewell-pharma.test"))
    assert other == body
    assert ok_json(w.bob.get("/dossiers")) == ok_json(w.ada.get("/dossiers"))


# ------------------------------------------------------------------ list
def seed_domains(w, domains):
    for d in domains:
        assert_status(w.request(w.ada, d), 202)


def test_list_order_shape_and_default_paging(world):
    """LS-1 LS-4 LS-6"""
    ds = ["zeta.test", "alpha.test", "mid.test", "beta.test"]
    seed_domains(world, ds)
    j = ok_json(world.bob.get("/dossiers"))
    assert j["has_more"] is False and set(j) == {"dossiers", "has_more"}
    assert [d["domain"] for d in j["dossiers"]] == sorted(ds)
    for d in j["dossiers"]:
        assert set(d) >= {"dossier_id", "domain", "state", "legal_name", "researched_at",
                          "spent_units"}
        assert isinstance(d["spent_units"], int)


def test_list_paging(world):
    """LS-5"""
    ds = [f"p{i:02d}.test" for i in range(7)]
    seed_domains(world, ds)
    got = []
    off = 0
    while True:
        j = ok_json(world.ada.get("/dossiers", params={"limit": 3, "offset": off}))
        got += [d["domain"] for d in j["dossiers"]]
        assert len(j["dossiers"]) <= 3
        if not j["has_more"]:
            break
        off += 3
    assert got == ds
    j = ok_json(world.ada.get("/dossiers", params={"limit": 7}))
    assert len(j["dossiers"]) == 7 and j["has_more"] is False
    j = ok_json(world.ada.get("/dossiers", params={"limit": 6}))
    assert len(j["dossiers"]) == 6 and j["has_more"] is True
    j = ok_json(world.ada.get("/dossiers", params={"offset": 7}))
    assert j == {"dossiers": [], "has_more": False}
    j = ok_json(world.ada.get("/dossiers", params={"offset": 100, "limit": 5}))
    assert j == {"dossiers": [], "has_more": False}
    j = ok_json(world.ada.get("/dossiers", params={"limit": "1", "offset": "6"}))
    assert [d["domain"] for d in j["dossiers"]] == [ds[6]] and j["has_more"] is False
    j = ok_json(world.ada.get("/dossiers", params={"limit": "05", "offset": "00"}))
    assert len(j["dossiers"]) == 5


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 201}, {"limit": -1}, {"offset": -1}, {"limit": "abc"},
    {"offset": "x"}, {"limit": "1e9"}, {"limit": "4.0"}, {"limit": "+4"}, {"offset": "1e1"},
    {"offset": "2.0"}, {"offset": "+0"}, {"limit": ""}, {"offset": ""}, {"limit": " 5"},
    {"limit": "0x10"}, {"limit": "99999999999999999999999"}, {"limit": "1_0"},
])
def test_invalid_paging(world, params):
    """LS-7 CV-8 CV-9"""
    err(world.ada.get("/dossiers", params=params), 422, "validation_failed")


def test_valid_limit_bounds_and_unknown_params(world):
    """CV-9 CV-3"""
    seed_domains(world, ["one.test"])
    for lim in ("1", "200"):
        assert len(ok_json(world.ada.get("/dossiers", params={"limit": lim}))["dossiers"]) == 1
    assert len(ok_json(world.ada.get("/dossiers", params={"zzz": "1", "sort": "desc"}))
               ["dossiers"]) == 1
    assert_status(world.ada.get("/dossiers/one.test", params={"foo": "bar"}), 200)


def test_list_q_filter(world):
    """LS-2 LS-3"""
    seed_domains(world, ["acme-robotics.test", "ACME-widgets.test", "boltworks.test",
                         "a-c-me.test", "xacmex.test"])
    names = lambda q: [d["domain"] for d in ok_json(world.ada.get("/dossiers", params={"q": q}))["dossiers"]]  # noqa: E731
    assert names("acme") == ["acme-robotics.test", "acme-widgets.test", "xacmex.test"]
    assert names("ACME") == names("acme")
    assert names("Robot") == ["acme-robotics.test"]
    assert names("") == sorted(["acme-robotics.test", "acme-widgets.test", "boltworks.test",
                                "a-c-me.test", "xacmex.test"])
    assert names("zzzz") == []
    assert names(".test") and len(names(".test")) == 5
    # a literal substring match, never a pattern
    assert names("a.c") == [] and names("%") == [] and names("_") == [] and names(".*") == []
    assert names("acme-r%") == [] and names("[a]") == [] and names("a|b") == []
    assert names("(acme") == []
    j = ok_json(world.ada.get("/dossiers", params={"q": "acme", "limit": 1, "offset": 1}))
    assert [d["domain"] for d in j["dossiers"]] == ["acme-widgets.test"] and j["has_more"] is True


def test_list_q_matches_legal_name_case_insensitively(pworld):
    """LS-2 LS-6"""
    w = pworld
    w.build(w.ada, "northwind-optics.test")
    w.build(w.ada, "no-trace.test")
    j = ok_json(w.ada.get("/dossiers", params={"q": "NORTHWIND OPTICS, INC"}))
    assert [d["domain"] for d in j["dossiers"]] == ["northwind-optics.test"]
    assert j["dossiers"][0]["legal_name"] == "Northwind Optics, Inc."
    assert ok_json(w.ada.get("/dossiers", params={"q": "optics, inc"}))["dossiers"]
    by = {d["domain"]: d for d in ok_json(w.ada.get("/dossiers"))["dossiers"]}
    assert by["no-trace.test"]["legal_name"] is None and by["no-trace.test"]["state"] == "ready"
    full = w.dossier(w.ada, "northwind-optics.test")
    e = by["northwind-optics.test"]
    assert (e["dossier_id"], e["state"], e["researched_at"], e["spent_units"]) == (
        full["dossier_id"], full["state"], full["researched_at"], full["spent_units"])


# ------------------------------------------------------------------ misc reads
def test_reads_and_validation_errors_make_no_provider_call(pworld):
    """GD-9 BD-6 H-2 PD-7"""
    w = pworld
    w.build(w.ada, "tidewell-pharma.test")
    mark = len(w.mock.log())
    w.anon.get("/health")
    w.ada.get("/dossiers")
    w.ada.get("/dossiers/tidewell-pharma.test")
    w.ada.get("/dossiers/WWW.Tidewell-Pharma.test.")
    w.ada.get("/dossiers/missing.test")
    w.ada.get("/dossiers/-bad-")
    w.ada.post("/dossiers/missing.test/refresh", key=new_key())
    w.request(w.ada, "https://bad.test")
    w.request(w.bob, "tidewell-pharma.test")                  # existing -> 200, no build
    w.request(w.bob, "WWW.TIDEWELL-PHARMA.TEST.")
    w.signup("q@example.com")
    w.anon.post("/auth/login", body={"email": "q@example.com", "password": "correct horse"})
    time.sleep(1.0)
    assert len(w.mock.log()) == mark, w.mock.log()[mark:]


def test_existing_dossier_post_is_200_and_reports_current_state(pworld):
    """PD-2"""
    w = pworld
    body, _ = w.build(w.ada, "tidewell-pharma.test")
    j = ok_json(w.bob.post("/dossiers", body={"domain": "TIDEWELL-PHARMA.test"}, key=new_key()), 200)
    assert j == {"dossier_id": body["dossier_id"], "domain": "tidewell-pharma.test",
                 "state": "ready"}
    w.mock.break_all()
    b2, _ = w.refresh(w.ada, "tidewell-pharma.test")
    assert b2["state"] == "failed"
    j = ok_json(w.bob.post("/dossiers", body={"domain": "tidewell-pharma.test"}, key=new_key()), 200)
    assert j["state"] == "failed"
