import threading
import time
import unittest

from dossier_service.builder import BuildResult
from dossier_service.errors import ApiError
from dossier_service.store import Store, unknown_fields

FIXTURE = {"now": "2026-03-01T09:00:00+00:00",
           "users": [{"id": "u_ada", "email": "ada@example.com", "password": "correct horse",
                      "display_name": "Ada"}]}


def build_fn(domain, on_spend, stopped):
    on_spend(7)
    fields = unknown_fields()
    fields["ceo"] = {"value": "Dana Ruiz", "status": "known",
                     "citations": [{"url": "https://x.test/a", "excerpt": "e", "provider": "nimble"}]}
    return BuildResult(fields, True)


def wait_built(store, domain):
    for _ in range(100):
        if store.get_dossier(domain)["state"] != "building":
            return store.get_dossier(domain)
        time.sleep(0.02)
    raise AssertionError("build did not finish")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(build_fn)
        self.store.reset(FIXTURE)

    def create(self, key, domain="acme.test"):
        return self.store.idempotent("u_ada", "POST", "/dossiers", key, domain,
                                     lambda: self.store.start_dossier(domain))

    def test_replay_and_reuse(self):
        first = self.create("k")
        self.assertEqual(first[0], 202)
        self.assertEqual(self.create("k"), (200, first[1]))
        with self.assertRaises(ApiError) as caught:
            self.create("k", "other.test")
        self.assertEqual(caught.exception.code, "idempotency_key_reuse")

    def test_concurrent_creates_start_one_build(self):
        results = []
        threads = [threading.Thread(target=lambda i=i: results.append(self.create(f"k{i}"))) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(r[0] for r in results), [200] * 19 + [202])
        self.assertEqual(wait_built(self.store, "acme.test")["spent_units"], 7)

    def test_export_import_round_trip(self):
        self.create("k")
        before = wait_built(self.store, "acme.test")
        snapshot = self.store.export_state()
        self.store.reset({"now": "2026-04-01T00:00:00+00:00"})
        self.store.import_state(snapshot)
        self.assertEqual(self.store.get_dossier("acme.test"), before)
        self.assertEqual(self.store.export_state(), snapshot)
        self.assertEqual(self.create("k")[0], 200)

    def test_invalid_import_changes_nothing(self):
        snapshot = self.store.export_state()
        with self.assertRaises(ApiError):
            self.store.import_state({"track": "dossier", "format_version": 1, "state": {"users": []}})
        self.assertEqual(self.store.export_state(), snapshot)

    def test_reset_rejects_duplicate_emails(self):
        user = FIXTURE["users"][0]
        with self.assertRaises(ApiError):
            self.store.reset({"now": FIXTURE["now"], "users": [user, {**user, "id": "u_2"}]})

    def test_clock_only_moves_forward(self):
        from dossier_service.clock import parse_timestamp
        with self.assertRaises(ApiError):
            self.store.clock.advance_to(parse_timestamp("2026-02-01T00:00:00+00:00"))


if __name__ == "__main__":
    unittest.main()
