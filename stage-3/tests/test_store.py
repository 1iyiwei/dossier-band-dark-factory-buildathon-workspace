import threading
import time
import unittest

from dossier_service.builder import BuildResult
from dossier_service.errors import ApiError
from dossier_service.selection import Candidate
from dossier_service.store import Store

FIXTURE = {"now": "2026-03-01T09:00:00+00:00",
           "users": [{"id": "u_ada", "email": "ada@example.com", "password": "correct horse",
                      "display_name": "Ada"}]}


def build_fn(domain, on_spend, stopped):
    on_spend(7)
    candidates = {name: [] for name in ("legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total")}
    candidates["ceo"] = [Candidate("Dana Ruiz", "https://x.test/a", "e", "nimble", "own", "2026-01-10T00:00:00+00:00")]
    return BuildResult(candidates, True)


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

    def test_build_result_follows_selection_rule(self):
        self.create("k")
        ceo = wait_built(self.store, "acme.test")["fields"]["ceo"]
        self.assertEqual((ceo["value"], ceo["status"]), ("Dana Ruiz", "known"))
        self.assertEqual(ceo["candidates"][0]["retrieved_at"], "2026-03-01T09:00:00+00:00")
        self.assertTrue(ceo["candidates"][0]["selected"])

    def test_import_of_stage_one_export_gains_candidates(self):
        stage_one = {"track": "dossier", "format_version": 1, "state": {
            "users": [{"id": "u_ada", "email": "ada@example.com", "display_name": "Ada", "password_hash": "x"}],
            "tokens": {"tok": "u_ada"},
            "dossiers": [{
                "dossier_id": "d_1", "domain": "acme.test", "state": "ready", "researched_at": "2026-03-01T09:00:00+00:00",
                "spent_units": 12,
                "fields": {
                    **{name: {"value": None, "status": "unknown", "citations": []}
                       for name in ("legal_name", "hq_city", "founded_year", "headcount_range", "funding_total")},
                    "ceo": {"value": "Dana Ruiz", "status": "known", "citations": [
                        {"url": "https://acme.test/b", "excerpt": "Dana Ruiz is the CEO of Acme.", "provider": "nimble"},
                        {"url": "https://acme.test/a", "excerpt": "Acme CEO: Dana Ruiz.", "provider": "nimble"}]}}}],
            "idempotency": [], "dossier_counter": 1}}
        self.store.import_state(stage_one)
        ceo = self.store.get_dossier("acme.test")["fields"]["ceo"]
        self.assertEqual([c["url"] for c in ceo["candidates"]], ["https://acme.test/a", "https://acme.test/b"])
        self.assertEqual([c["selected"] for c in ceo["candidates"]], [True, False])
        self.assertEqual(ceo["candidates"][0]["kind"], None)
        self.assertEqual(ceo["candidates"][0]["published_at"], None)
        self.assertEqual(ceo["candidates"][0]["retrieved_at"], "2026-03-01T09:00:00+00:00")
        self.assertEqual(len(ceo["citations"]), 2)
        self.assertEqual(self.store.get_dossier("acme.test")["fields"]["hq_city"]["candidates"], [])
        self.assertEqual(self.store.authenticate("tok"), "u_ada")

    def test_stage_one_import_derives_candidates_for_every_field_a_cited_excerpt_supports(self):
        excerpt = "Dana Ruiz, CEO of Acme, is based in Lisbon."
        fields = {name: {"value": None, "status": "unknown", "citations": []}
                  for name in ("legal_name", "founded_year", "headcount_range", "funding_total")}
        fields["ceo"] = {"value": "Dana Ruiz", "status": "known", "citations": [
            {"url": "https://acme.test/a", "excerpt": excerpt, "provider": "nimble"},
            {"url": "https://acme.test/a", "excerpt": "Acme CEO: Dana Ruiz.", "provider": "nimble"}]}
        fields["hq_city"] = {"value": "Lisbon", "status": "known", "citations": [
            {"url": "https://acme.test/a", "excerpt": excerpt, "provider": "nimble"}]}
        self.store.import_state({"track": "dossier", "format_version": 1, "state": {
            "users": [], "tokens": {}, "idempotency": [], "dossier_counter": 1,
            "dossiers": [{"dossier_id": "d_1", "domain": "acme.test", "state": "ready", "spent_units": 1,
                          "researched_at": "2026-03-01T09:00:00+00:00", "fields": fields}]}})
        stored = self.store.get_dossier("acme.test")["fields"]
        self.assertEqual([c["value"] for c in stored["ceo"]["candidates"]], ["Dana Ruiz"])
        self.assertEqual([c["value"] for c in stored["hq_city"]["candidates"]], ["Lisbon"])

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


class ImportDomainTests(unittest.TestCase):
    def test_export_with_www_prefixed_domain_imports(self):
        store = Store(build_fn)
        store.reset(FIXTURE)
        store.start_dossier("www.acme.test")      # as created by {"domain": "www.www.acme.test"}
        wait_built(store, "www.acme.test")
        snapshot = store.export_state()
        store.import_state(snapshot)
        self.assertEqual(store.export_state(), snapshot)
