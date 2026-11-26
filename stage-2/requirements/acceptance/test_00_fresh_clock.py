"""Clock before the first reset (needs BASE_URL_2: a fresh instance nobody has reset yet).
Runs first (file order). Ledger: CK-8."""
import time
from datetime import datetime, timezone

import pytest

from conftest import BASE2, PW, Api, assert_status, ok_json, parse_ts, new_key


@pytest.mark.skipif(not BASE2, reason="BASE_URL_2 (fresh instance) not provided")
def test_clock_follows_system_time_before_the_first_reset():
    """CK-8"""
    api = Api(BASE2)
    s = ok_json(api.post("/auth/signup", body={"email": "fresh@example.com", "password": PW,
                                              "display_name": "Fresh"}), 201)
    me = Api(BASE2, s["token"])
    assert_status(me.post("/dossiers", body={"domain": "tidewell-pharma.test"}, key=new_key()), 202)
    end = time.time() + 30
    while True:
        b = ok_json(me.get("/dossiers/tidewell-pharma.test"))
        if b["state"] != "building" or time.time() > end:
            break
        time.sleep(0.2)
    assert b["state"] == "ready" and b["researched_at"]
    drift = abs((parse_ts(b["researched_at"]) - datetime.now(timezone.utc)).total_seconds())
    assert drift < 120, f"before the first reset the clock follows the system time (drift {drift}s)"
