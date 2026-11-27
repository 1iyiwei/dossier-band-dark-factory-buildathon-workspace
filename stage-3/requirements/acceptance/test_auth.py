"""Authentication, conventions, reset/clock. Ledger IDs in each docstring."""
import pytest

from conftest import (ADA, BOB, BASE, NOW0, PW, Api, assert_status, check_error_envelope, err,
                      fixture, new_key, ok_json, parse_ts, pmap)


def test_health(world):
    """H-1"""
    r = assert_status(world.anon.get("/health"), 200)
    assert r.json() == {"status": "ok"}


def test_signup_login_shapes(world):
    """AU-1 AU-2 CV-4"""
    s = ok_json(world.signup("dee@example.com", PW, "Dee"), 201)
    assert set(s) >= {"user_id", "display_name", "token"} and s["display_name"] == "Dee"
    assert isinstance(s["user_id"], str) and 1 <= len(s["user_id"]) <= 64 and s["token"]
    api = Api(BASE, s["token"])                       # token works at once
    assert_status(api.get("/dossiers"), 200)
    lg = ok_json(world.anon.post("/auth/login", body={"email": "dee@example.com", "password": PW}))
    assert lg["user_id"] == s["user_id"] and lg["display_name"] == "Dee" and lg["token"]
    assert_status(Api(BASE, lg["token"]).get("/dossiers"), 200)


def test_seeded_users_log_in_with_their_ids(world):
    """R-7"""
    for u in (ADA, BOB):
        j = ok_json(world.anon.post("/auth/login", body={"email": u["email"], "password": PW}))
        assert j["user_id"] == u["id"] and j["display_name"] == u["display_name"]


def test_duplicate_email(world):
    """AU-3"""
    assert_status(world.signup("dup@example.com"), 201)
    err(world.signup("dup@example.com"), 409, "email_taken")
    err(world.signup(ADA["email"]), 409, "email_taken")


@pytest.mark.parametrize("pw,status", [("", 422), ("1234567", 422), ("é" * 7, 422),
                                       ("12345678", 201), ("é" * 8, 201)])
def test_password_length_is_in_characters(world, pw, status):
    """AU-4"""
    r = world.signup(f"p{abs(hash(pw))}@example.com", pw)
    if status == 422:
        err(r, 422, "validation_failed")
    else:
        assert_status(r, 201)


@pytest.mark.parametrize("email", ["plain", "@example.com", "dee@", "", "a@@b.com"])
def test_email_form(world, email):
    """AU-5"""
    err(world.signup(email), 422, "validation_failed")


@pytest.mark.parametrize("name,status", [("", 422), ("x" * 101, 422), ("x" * 100, 201),
                                         ("é" * 100, 201), ("é" * 101, 422), ("A", 201)])
def test_display_name_range(world, name, status):
    """AU-6"""
    r = world.signup(f"n{len(name)}{abs(hash(name))}@example.com", PW, name)
    if status == 422:
        err(r, 422, "validation_failed")
    else:
        assert_status(r, 201)


@pytest.mark.parametrize("email,pw", [(ADA["email"], "wrong horse"), ("nobody@example.com", PW)])
def test_login_failures(world, email, pw):
    """AU-7"""
    err(world.anon.post("/auth/login", body={"email": email, "password": pw}), 401,
        "unauthenticated")


@pytest.mark.parametrize("path", ["/auth/signup", "/auth/login"])
def test_auth_bodies_unparseable_or_wrong_type(world, path):
    """AU-13 CV-7"""
    err(world.anon.post(path, raw=b"{not json"), 400, "malformed_request")
    err(world.anon.post(path, raw=b"[1,2]"), 400, "malformed_request")
    full = {"email": "t@example.com", "password": PW, "display_name": "T"}
    for field, bad in (("email", 7), ("password", ["x"]), ("display_name", {"a": 1})):
        if path == "/auth/login" and field == "display_name":
            continue
        body = dict(full, **{field: bad})
        err(world.anon.post(path, body=body), 400, "malformed_request")


@pytest.mark.parametrize("field", ["email", "password", "display_name"])
def test_signup_missing_field(world, field):
    """AU-13"""
    body = {"email": "m@example.com", "password": PW, "display_name": "M"}
    del body[field]
    err(world.anon.post("/auth/signup", body=body), 422, "validation_failed")


def test_unknown_body_fields_ignored(world):
    """CV-2"""
    assert_status(world.anon.post("/auth/signup", body={
        "email": "x1@example.com", "password": PW, "display_name": "X", "role": "admin",
        "extra": {"a": 1}}), 201)
    assert_status(world.anon.post("/auth/login", body={
        "email": "x1@example.com", "password": PW, "zzz": 1}), 200)


ENDPOINTS = [("GET", "/dossiers"), ("GET", "/dossiers/acme.test"),
             ("POST", "/dossiers"), ("POST", "/dossiers/acme.test/refresh")]


@pytest.mark.parametrize("method,path", ENDPOINTS)
@pytest.mark.parametrize("auth", [None, "Bearer", "Bearer a b", "Bearer nope", "Basic abc",
                                  "Token abc", "nope"])
def test_endpoints_need_a_valid_bearer_token(world, method, path, auth):
    """AU-8 AU-9 AU-12 (also: 401 even when the idempotency key is missing/body invalid)"""
    h = {} if auth is None else {"Authorization": auth}
    kw = {"body": {"domain": "acme.test"}} if method == "POST" else {}
    err(world.anon.req(method, path, headers=h, **kw), 401, "unauthenticated")
    err(world.anon.req(method, path, headers=h, raw=b"garbage" if method == "POST" else None),
        401, "unauthenticated")


def test_tokens_are_multiple_and_valid_together(world):
    """AU-10"""
    toks = [ok_json(world.anon.post("/auth/login", body={"email": ADA["email"], "password": PW}))
            ["token"] for _ in range(3)]
    s = ok_json(world.signup("multi@example.com"), 201)["token"]
    l1 = ok_json(world.anon.post("/auth/login", body={"email": "multi@example.com",
                                                      "password": PW}))["token"]
    for t in toks + [s, l1, world.ada.token]:
        assert_status(Api(BASE, t).get("/dossiers"), 200)


def test_concurrent_signup_same_email(world):
    """AU-14 CC-2"""
    rs = pmap(lambda i: world.signup("race@example.com", PW, f"R{i}"), range(12))
    codes = sorted(r.status_code for r in rs)
    assert codes == [201] + [409] * 11, codes
    for r in rs:
        if r.status_code == 409:
            check_error_envelope(r)


def test_concurrent_signups_distinct(world):
    """AU-14 CC-1"""
    rs = pmap(lambda i: world.signup(f"c{i}@example.com", PW, f"C{i}"), range(30))
    js = [ok_json(r, 201) for r in rs]
    assert len({j["user_id"] for j in js}) == 30 and len({j["token"] for j in js}) == 30


def test_unknown_route_and_method_use_the_error_envelope(world):
    """CV-6"""
    r = world.ada.get("/no/such/route")
    assert r.status_code in (404, 405) and check_error_envelope(r)
    r = world.ada.req("DELETE", "/dossiers")
    assert r.status_code in (404, 405) and check_error_envelope(r)
    err(world.ada.get("/dossiers/missing.test"), 404, "not_found")


def test_content_type_of_json_responses(world):
    """CV-1"""
    for r in (world.anon.get("/health"), world.ada.get("/dossiers"),
              world.anon.post("/auth/login", body={"email": ADA["email"], "password": PW})):
        assert r.headers["content-type"].lower().replace(" ", "") == "application/json;charset=utf-8"


# ------------------------------------------------------------------ reset
def test_reset_removes_users_and_tokens(world):
    """R-1 R-5"""
    tok = ok_json(world.signup("gone@example.com"), 201)["token"]
    old_ada = world.ada.token
    world.reset(fixture(users=[BOB]))
    err(world.anon.post("/auth/login", body={"email": "gone@example.com", "password": PW}), 401,
        "unauthenticated")
    err(world.anon.post("/auth/login", body={"email": ADA["email"], "password": PW}), 401,
        "unauthenticated")
    err(Api(BASE, tok).get("/dossiers"), 401, "unauthenticated")
    err(Api(BASE, old_ada).get("/dossiers"), 401, "unauthenticated")
    assert_status(world.bob.get("/dossiers"), 200)


def test_reset_repeated_and_unauthenticated(world):
    """R-2 R-4"""
    for _ in range(3):
        r = world.anon.post("/_test/reset", body=fixture(), timeout=10)
        assert r.status_code == 204 and r.content == b""
    world.reset()
    assert ok_json(world.ada.get("/dossiers")) == {"dossiers": [], "has_more": False}


def test_reset_duplicate_emails_changes_nothing(world):
    """R-5"""
    r = world.anon.post("/_test/reset", body=fixture(users=[ADA, dict(BOB, email=ADA["email"])]),
                        timeout=10)
    err(r, 422, "validation_failed")
    assert_status(world.ada.get("/dossiers"), 200)      # old token still valid


def test_reset_requires_now(world):
    """R-6"""
    err(world.anon.post("/_test/reset", body={"users": []}, timeout=10), 422, "validation_failed")
    assert_status(world.ada.get("/dossiers"), 200)


def test_reset_accepts_empty_users_and_ignores_unknown_fields(world):
    """R-1 CV-2"""
    assert_status(world.anon.post("/_test/reset", body={"now": NOW0, "users": [], "zz": 1},
                                  timeout=10), 204)
    err(world.anon.post("/auth/login", body={"email": ADA["email"], "password": PW}), 401,
        "unauthenticated")
    world.reset()


# ------------------------------------------------------------------ clock
def test_clock_rejects_earlier_instants_across_offsets(world):
    """CK-3 CK-4"""
    assert_status(world.clock("2026-03-01T09:00:00+00:00"), 204)
    # 10:30+02:00 is 08:30Z: earlier than 09:00Z although its text sorts later
    err(world.clock("2026-03-01T10:30:00+02:00"), 422, "validation_failed")
    err(world.clock("2026-03-01T08:59:59+00:00"), 422, "validation_failed")
    assert_status(world.clock("2026-03-01T09:00:00+00:00"), 204)        # equal is not earlier
    assert_status(world.clock("2026-03-01T11:30:00+02:00"), 204)        # 09:30Z, later


@pytest.mark.parametrize("now", ["2026-03-02T09:00:00", "2026-03-02", "yesterday", "", "2026-13-01T00:00:00+00:00"])
def test_clock_needs_an_rfc3339_timestamp_with_offset(world, now):
    """CK-5"""
    err(world.clock(now), 422, "validation_failed")


def test_clock_wrong_type_and_missing(world):
    """CK-6"""
    err(world.anon.post("/_test/clock", body={"now": 5}), 400, "malformed_request")
    err(world.anon.post("/_test/clock", raw=b"{oops"), 400, "malformed_request")
    err(world.anon.post("/_test/clock", body={}), 422, "validation_failed")


def test_reset_forgets_stored_idempotent_responses(world):
    """R-1 ID-8"""
    k = new_key()
    assert_status(world.ada.post("/dossiers", body={"domain": "forget-a.test"}, key=k), 202)
    world.reset()
    # the same key with a different body is a first use again: no 409, no stale replay
    j = ok_json(world.ada.post("/dossiers", body={"domain": "forget-b.test"}, key=k), 202)
    assert j["domain"] == "forget-b.test"
    world.reset()
    j = ok_json(world.ada.post("/dossiers", body={"domain": "forget-a.test"}, key=k), 202)
    assert j["state"] == "building"          # not a replay (would be 200)
