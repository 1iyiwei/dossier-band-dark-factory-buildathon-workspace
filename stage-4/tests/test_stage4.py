import http.client
import json
import os
import tempfile
import threading
import unittest

from dossier_service.builder import BuildResult
from dossier_service.clock import parse_timestamp
from dossier_service.corroboration import corroborated_since
from dossier_service.dossier import entry_type
from dossier_service.evidence import Evidence
from dossier_service.http_server import Server
from dossier_service.lineage import PageLineage, origin_of, parse_lineage
from dossier_service.persistence import Journal
from dossier_service.selection import Candidate, investors_of
from dossier_service.store import Store
from dossier_service.support import supported_investors
from dossier_service.versions import PageVersion

DOMAIN = "acme-robotics.test"
FIXTURE = {"now": "2026-03-01T09:00:00+00:00",
           "users": [{"id": "u_ada", "email": "ada@example.com", "password": "correct horse", "display_name": "Ada"},
                     {"id": "u_bob", "email": "bob@example.com", "password": "correct horse", "display_name": "Bob"}]}


class InvestorTests(unittest.TestCase):
    def names(self, excerpt):
        return supported_investors(excerpt, DOMAIN)

    def test_suffix_names(self):
        self.assertEqual(self.names("Bluebird Capital is an investor in Acme Robotics."), ["Bluebird Capital"])
        self.assertEqual(self.names("Acme Robotics investors include Northwind Ventures and Bluebird Capital."),
                         ["Northwind Ventures", "Bluebird Capital"])
        self.assertEqual(self.names("Acme Robotics is backed by Old Mill Holdings."), ["Old Mill Holdings"])

    def test_name_after_led_by_needs_an_amount(self):
        self.assertEqual(self.names("Acme Robotics raised $40M in a round led by General Atlantic."), ["General Atlantic"])
        self.assertEqual(self.names("Acme Robotics is led by Dana Ruiz."), [])
        self.assertEqual(self.names("Acme Robotics investors include General Atlantic."), [])

    def test_rules_one_to_four_of_a2(self):
        self.assertEqual(self.names("Bluebird Capital is an investor in another company."), [])    # does not name it
        self.assertEqual(self.names("Bluebird Capital is not an investor in Acme Robotics."), [])  # negating phrase
        self.assertEqual(self.names("Bluebird Capital. An investor in Acme Robotics."), [])        # two sentences
        self.assertEqual(self.names("Ventures is an investor in Acme Robotics."), [])              # a name has two words

    def test_runs_are_maximal_and_single_word_suffix_is_no_name(self):
        self.assertEqual(self.names("Capital is an investor in Acme Robotics."), [])
        self.assertEqual(self.names("Acme Robotics investor Big Blue Capital Fund."), ["Big Blue Capital Fund"])


class LineageTests(unittest.TestCase):
    def lineage(self, url, **header):
        return parse_lineage(header, url)

    def origin(self, page, pages=None):
        return origin_of(page, DOMAIN, lambda url: (pages or {}).get(url))

    def test_registrant_defaults_to_the_host(self):
        self.assertEqual(self.lineage("https://www.news.test/a").registrant, "news.test")
        self.assertEqual(self.lineage("https://news.test/a", Registrant="Daily-Ledger.TEST.").registrant,
                         "daily-ledger.test")
        self.assertEqual(self.lineage("https://news.test/a", Registrant="not a domain").registrant, "news.test")

    def test_rule_order(self):
        copy = self.lineage("https://copy.test/a", Canonical="https://orig.test/a", **{"First-Published-By": "wire.test"})
        self.assertEqual(self.origin(copy), "wire.test")
        copy = self.lineage("https://copy.test/a", Canonical="https://orig.test/a")
        self.assertEqual(self.origin(copy, {"https://orig.test/a": self.lineage("https://orig.test/a")}), "orig.test")
        self.assertEqual(self.origin(copy), "orig.test")           # no page served there: the host of the URL
        lookalike = self.lineage("https://acme-robotics-inc.test/", Kind="own", Registrant="shell-holdings.test")
        self.assertTrue(lookalike.lookalike)
        self.assertEqual(self.origin(lookalike), DOMAIN)
        self.assertEqual(self.origin(self.lineage("https://news.test/a", Registrant="ledger.test")), "ledger.test")

    def test_a_canonical_url_that_is_the_page_itself_is_no_copy(self):
        page = self.lineage("https://news.test/a", Canonical="https://news.test/a")
        self.assertIsNone(page.canonical)

    def test_at_most_three_canonical_urls_are_followed(self):
        pages = {f"https://c{i}.test/": self.lineage(f"https://c{i}.test/", Canonical=f"https://c{i + 1}.test/")
                 for i in range(2, 8)}
        first = self.lineage("https://c1.test/", Canonical="https://c2.test/")
        self.assertEqual(self.origin(first, pages), "c5.test")     # c2, c3, c4 followed; c4's canonical is a fourth

    def test_own_pages_need_the_company_as_registrant(self):
        evidence = Evidence(DOMAIN)
        text = "Kind: own\nRegistrant: other.test\n\nAcme Robotics CEO: Sam Ortiz."
        evidence.add_page("https://acme-robotics.test/about", "nimble", text)
        evidence.add_page("https://acme-robotics.test/team", "nimble", "Kind: own\n\nAcme Robotics CEO: Dana Ruiz.")
        (stated_other, own) = evidence.pages()
        self.assertEqual(stated_other.candidates[0][1].kind, "aggregator")
        self.assertEqual(own.candidates[0][1].kind, "own")
        self.assertEqual(own.candidates[0][1].origin, DOMAIN)

    def test_originals_are_looked_up_only_when_a_candidate_needs_them(self):
        evidence = Evidence(DOMAIN)
        evidence.add_page("https://copy.test/a", "nimble", "Canonical: https://orig.test/a\n\nAcme Robotics CEO: Sam Ortiz.")
        evidence.add_page("https://copy.test/b", "nimble", "Canonical: https://other.test/b\n\nNothing to see.")
        self.assertEqual(evidence.unresolved(), ["https://orig.test/a"])
        evidence.note_served("https://orig.test/a", "Registrant: wire.test\n\ntext")
        self.assertEqual(evidence.unresolved(), [])
        self.assertEqual(evidence.pages()[0].candidates[0][1].origin, "wire.test")


def view(value, origins_by_value, members=None):
    """A single field as a build left it: candidates (value, origin) pairs."""
    return {"value": value, "candidates": [{"value": v, "origin": o} for v, o in origins_by_value]}


class CorroborationTests(unittest.TestCase):
    def test_standing_origins_accumulate_since_the_value_was_selected(self):
        series = [("t1", view("A", [("A", "x.test")])),
                  ("t2", view("A", [("A", "y.test")])),
                  ("t3", view("A", [("A", "x.test")]))]
        self.assertIsNone(corroborated_since("ceo", series[:1]))
        self.assertEqual(corroborated_since("ceo", series[:2]), "t2")
        self.assertEqual(corroborated_since("ceo", series), "t2")      # a later build that lost y.test still stands

    def test_a_new_selected_value_starts_with_none(self):
        series = [("t1", view("A", [("A", "x.test"), ("A", "y.test")])),
                  ("t2", view("B", [("B", "x.test"), ("A", "y.test")]))]
        self.assertEqual(corroborated_since("ceo", series[:1]), "t1")
        self.assertIsNone(corroborated_since("ceo", series))

    def test_unknown_field_is_not_corroborated(self):
        self.assertIsNone(corroborated_since("ceo", [("t1", view(None, []))]))

    def test_members_are_each_counted_from_when_they_became_one(self):
        def investors(names, candidates):
            return {"value": names, "candidates": [{"value": n, "origin": o} for n, o in candidates]}

        series = [("t1", investors(["A"], [("A", "x.test"), ("A", "y.test")])),
                  ("t2", investors(["A", "B"], [("A", "x.test"), ("B", "x.test")])),
                  ("t3", investors(["A", "B"], [("A", "x.test"), ("B", "z.test")]))]
        self.assertEqual(corroborated_since("investors", series[:1]), "t1")
        self.assertIsNone(corroborated_since("investors", series[:2]))
        self.assertEqual(corroborated_since("investors", series), "t3")


def cand(name, kind="news", origin="x.test", true_from=None, url="https://x.test/p"):
    return Candidate(name, url, f"{name} invested in Acme Robotics.", "nimble", kind, None, true_from=true_from, origin=origin)


class InvestorFieldTests(unittest.TestCase):
    def test_members_are_own_or_filing_names_or_names_with_two_origins(self):
        view = investors_of([cand("Alpha Capital", kind="filing"), cand("Beta Ventures"), cand("Gamma Fund", origin="x.test"),
                             cand("Gamma Fund", origin="y.test", url="https://y.test/p")])
        self.assertEqual(view["value"], ["Alpha Capital", "Gamma Fund"])
        self.assertEqual(view["status"], "known")
        self.assertEqual({c["value"]: c["selected"] for c in view["candidates"]},
                         {"Alpha Capital": True, "Beta Ventures": False, "Gamma Fund": True})
        self.assertEqual(view["origins"], ["x.test", "y.test"])
        self.assertFalse(view["corroborated"])           # Alpha Capital has one origin

    def test_no_member_is_unknown_but_keeps_candidates(self):
        view = investors_of([cand("Beta Ventures")])
        self.assertEqual((view["value"], view["status"], view["citations"], view["origins"]), (None, "unknown", [], []))
        self.assertEqual(len(view["candidates"]), 1)

    def test_true_from_is_the_latest_of_the_members_earliest(self):
        view = investors_of([cand("A Capital", kind="own", true_from="2024-05-02"),
                             cand("A Capital", kind="own", true_from="2023-01-01", url="https://x.test/q"),
                             cand("B Capital", kind="own", true_from="2025-01-01")])
        self.assertEqual(view["true_from"], "2025-01-01")
        self.assertIsNone(investors_of([cand("A Capital", kind="own", true_from="2024-05-02"),
                                        cand("B Capital", kind="own")])["true_from"])

    def entry(self, before, after):
        return entry_type("investors", investors_of(before), investors_of(after))

    def test_entry_types(self):
        old = [cand("A Capital", kind="own", true_from="2024-05-02")]
        self.assertIsNone(self.entry(old, old))
        added = old + [cand("B Capital", kind="own", true_from="2024-01-01")]
        self.assertEqual(self.entry(old, added), "correction")                 # the new name holds no later
        later = old + [cand("B Capital", kind="own", true_from="2025-01-01")]
        self.assertEqual(self.entry(old, later), "change")
        self.assertEqual(self.entry(old, []), "change")                        # a name that left is never a correction
        self.assertEqual(self.entry([], old), "change")


class FieldOrderTests(unittest.TestCase):
    """Every response that lists a dossier's fields holds investors after executives."""
    ORDER = ["legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total", "executives",
             "investors"]

    def test_values_history_dossier_and_as_of_list_fields_in_order(self):
        def build(domain, ledger, stopped):
            page = PageVersion("https://x.test/a", "2026-01-01", (("investors", cand("Alpha Capital", kind="own")),))
            return BuildResult([page], True)

        store = Store(build)
        store.reset(FIXTURE)
        store.start_dossier("a.test")
        for _ in range(500):
            if store.get_dossier("a.test")["state"] == "ready":
                break
            threading.Event().wait(0.01)
        as_of = parse_timestamp("2026-03-01T09:00:00+00:00")
        responses = [store.get_dossier("a.test")["fields"], store.get_dossier("a.test", as_of)["fields"],
                     store.values_at("a.test", "2026-02-01", None, None)["fields"],
                     store.history("a.test")["fields"]]
        imported = Store(build)
        imported.import_state(store.export_state())
        responses.append(imported.get_dossier("a.test")["fields"])
        for fields in responses:
            self.assertEqual(list(fields), self.ORDER)
        self.assertEqual(store.values_at("a.test", "2026-02-01", None, None)["fields"]["investors"]["value"],
                         ["Alpha Capital"])


class BatchStoreTests(unittest.TestCase):
    """Batches through the store, with builds that spend what the test says."""

    def setUp(self):
        self.spend = {}
        self.release = threading.Event()
        self.store = Store(self.build)
        self.store.reset(FIXTURE)

    def build(self, domain, ledger, stopped):
        self.release.wait(5)
        for cost in self.spend.get(domain, [10, 10, 10]):
            try:
                ledger.reserve(cost)
            except Exception:   # noqa: BLE001 - the budget is out
                break
            ledger.settle(cost, True)
        return BuildResult([], True)

    def wait_done(self, batch_id, user="u_ada"):
        for _ in range(500):
            view = self.store.get_batch(user, batch_id)
            if view["state"] == "done":
                return view
            threading.Event().wait(0.01)
        raise AssertionError("batch did not finish")

    def test_a_shared_budget_is_never_exceeded(self):
        self.release.set()
        _, body = self.store.start_batch("u_ada", ["a.test", "b.test"], 45)
        self.assertEqual(body["state"], "running")
        view = self.wait_done(body["batch_id"])
        self.assertEqual(view["spent_units"], 40)
        self.assertEqual(sum(self.store.get_dossier(d)["spent_units"] for d in ("a.test", "b.test")), 40)
        _, body = self.store.start_batch("u_ada", ["c.test", "d.test"], 25)
        self.assertEqual(self.wait_done(body["batch_id"])["spent_units"], 20)

    def test_a_build_spends_at_most_eighty(self):
        self.release.set()
        self.spend["a.test"] = [30, 30, 30, 30]
        _, body = self.store.start_batch("u_ada", ["a.test"], 1000)
        self.assertEqual(self.wait_done(body["batch_id"])["spent_units"], 60)

    def test_existing_dossiers_cost_the_batch_nothing(self):
        self.release.set()
        self.store.start_dossier("a.test")
        _, body = self.store.start_batch("u_ada", ["a.test", "b.test"], 100)
        self.assertEqual([d["domain"] for d in body["dossiers"]], ["a.test", "b.test"])
        self.assertEqual(self.wait_done(body["batch_id"])["spent_units"], 30)

    def test_another_users_batch_is_not_found(self):
        self.release.set()
        _, body = self.store.start_batch("u_ada", ["a.test"], 100)
        with self.assertRaises(Exception) as caught:
            self.store.get_batch("u_bob", body["batch_id"])
        self.assertEqual(caught.exception.status, 404)

    def test_batches_survive_export_and_import(self):
        self.release.set()
        _, body = self.store.start_batch("u_ada", ["a.test"], 100)
        expected = self.wait_done(body["batch_id"])
        other = Store(self.build)
        other.import_state(self.store.export_state())
        self.assertEqual(other.get_batch("u_ada", body["batch_id"]), expected)


class RestartTests(unittest.TestCase):
    def test_a_build_the_stop_found_running_ends_failed_with_every_unit_counted(self):
        started = threading.Event()
        hold = threading.Event()

        def build(domain, ledger, stopped):
            ledger.reserve(7)
            ledger.settle(7, True)
            ledger.reserve(3)                  # a call in flight at the stop
            started.set()
            hold.wait(10)
            return BuildResult([], False)

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.journal")
            first = Store(build, Journal(path))
            first.reset(FIXTURE)
            _, body = first.start_batch("u_ada", ["a.test", "b.test"], 100)
            self.assertTrue(started.wait(5))
            threading.Event().wait(0.2)
            reloaded = Store(lambda *a: None, Journal(path))       # the process was killed: nothing else is written
            hold.set()
            view = reloaded.get_batch("u_ada", body["batch_id"])
            self.assertEqual(view["state"], "done")
            self.assertEqual({d["state"] for d in view["dossiers"]}, {"failed"})
            for domain in ("a.test", "b.test"):
                self.assertEqual(reloaded.get_dossier(domain)["spent_units"], 10)
            self.assertEqual(view["spent_units"], 20)
            self.assertEqual(reloaded.refresh_dossier("a.test")[0], 202)
            history = reloaded.history("a.test")
            self.assertTrue(all(entries == [] for entries in history["fields"].values()))


class BatchHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def build(domain, ledger, stopped):
            return BuildResult([], True)

        cls.store = Store(build)
        cls.server = Server(("127.0.0.1", 0), cls.store)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.store.reset(FIXTURE)
        self.conn = http.client.HTTPConnection("127.0.0.1", self.port)
        self.conn.request("POST", "/auth/login", json.dumps({"email": "ada@example.com", "password": "correct horse"}))
        self.token = json.loads(self.conn.getresponse().read())["token"]

    def tearDown(self):
        self.conn.close()

    def post(self, body, key="k"):
        headers = {"Authorization": "Bearer " + self.token, **({"Idempotency-Key": key} if key else {})}
        self.conn.request("POST", "/batches", json.dumps(body), headers)
        response = self.conn.getresponse()
        return response.status, json.loads(response.read())

    def test_validation(self):
        good = {"domains": ["a.test"], "budget_units": 10}
        cases = [({**good, "domains": []}, 422), ({**good, "domains": ["a.test"] * 51}, 422),
                 ({**good, "domains": ["a.test", "WWW.a.test."]}, 422), ({**good, "domains": ["http://a.test"]}, 422),
                 ({"domains": ["a.test"]}, 422), ({**good, "budget_units": "10"}, 422), ({**good, "budget_units": True}, 422),
                 ({**good, "budget_units": 1.5}, 422), ({**good, "budget_units": 0}, 422),
                 ({**good, "budget_units": 100001}, 422), ({"budget_units": 10}, 422), ({**good, "domains": "a.test"}, 400)]
        for index, (body, status) in enumerate(cases):
            with self.subTest(body=body):
                self.assertEqual(self.post(body, f"key-{index}")[0], status)

    def test_create_replay_and_conflict(self):
        status, body = self.post({"domains": ["WWW.A.test", "b.test"], "budget_units": 10})
        self.assertEqual((status, body["state"], body["budget_units"], body["spent_units"]), (202, "running", 10, 0))
        self.assertEqual([d["domain"] for d in body["dossiers"]], ["a.test", "b.test"])
        self.assertEqual(self.post({"domains": ["WWW.A.test", "b.test"], "budget_units": 10})[0], 200)
        self.assertEqual(self.post({"domains": ["a.test", "b.test"], "budget_units": 10})[0], 409)
        self.assertEqual(self.post({"domains": ["a.test"], "budget_units": 10}, key=None)[0], 400)


if __name__ == "__main__":
    unittest.main()
