import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone

from dossier_service.builder import BuildResult
from dossier_service.clock import parse_timestamp
from dossier_service.errors import ApiError
from dossier_service.evidence import Evidence
from dossier_service.persistence import Journal
from dossier_service.selection import Candidate
from dossier_service.store import Store
from dossier_service.support import supported_value
from dossier_service.versions import PageVersion, holding, page_true_from

FIXTURE = {"now": "2026-03-01T09:00:00+00:00", "users": []}
T0 = "2026-03-01T09:00:00+00:00"


def cand(value, url="https://a.test/p", true_from=None, kind="own", published=None):
    return Candidate(value, url, f"excerpt {value}", "nimble", kind, published, true_from=true_from)


def page(url, true_from, **slots):
    return PageVersion(url, true_from, tuple((slot, cand(v, url, true_from)) for slot, v in slots.items()))


class ScriptedStore:
    """A store whose builds gather what the test says, one scripted result per build."""

    def __init__(self, journal=None):
        self.script = []
        self.store = Store(self._build, journal)
        self.store.reset(FIXTURE)

    def _build(self, domain, on_spend, stopped):
        on_spend(5)
        pages = self.script.pop(0)
        return BuildResult(pages, pages is not None)

    def build(self, pages, now=None):
        if now is not None:
            self.store.advance_clock(parse_timestamp(now))
        self.script.append(pages)
        if "acme.test" in self.store._dossiers:
            self.store.refresh_dossier("acme.test")
        else:
            self.store.start_dossier("acme.test")
        for _ in range(500):
            if self.store.get_dossier("acme.test")["state"] != "building":
                return
            threading.Event().wait(0.01)
        raise AssertionError("build did not finish")


class VersionTests(unittest.TestCase):
    def values(self, builds, true_at):
        return sorted(c.value for cs in holding(builds, true_at).values() for c in cs)

    def test_later_version_ends_the_earlier_one(self):
        builds = [[page("u", "2020-01-01", ceo="A")], [page("u", "2022-01-01", ceo="B")]]
        self.assertEqual(self.values(builds, "2019-12-31"), [])
        self.assertEqual(self.values(builds, "2021-06-01"), ["A"])
        self.assertEqual(self.values(builds, "2022-01-01"), ["B"])

    def test_later_version_replaces_versions_on_or_after_its_date(self):
        builds = [[page("u", "2020-01-01", ceo="A")], [page("u", "2022-01-01", ceo="B")],
                  [page("u", "2021-01-01", ceo="C")]]
        self.assertEqual(self.values(builds, "2020-06-01"), ["A"])
        self.assertEqual(self.values(builds, "2022-06-01"), ["C"])

    def test_empty_version_still_ends_the_earlier_one(self):
        builds = [[page("u", "2020-01-01", ceo="A")], [PageVersion("u", "2021-01-01", ())]]
        self.assertEqual(self.values(builds, "2020-06-01"), ["A"])
        self.assertEqual(self.values(builds, "2021-06-01"), [])

    def test_null_true_from_holds_never_and_replaces_everything(self):
        builds = [[page("u", "2020-01-01", ceo="A")], [page("u", None, ceo="B")]]
        self.assertEqual(self.values(builds, "2030-01-01"), [])
        builds.append([page("u", "2021-01-01", ceo="C")])
        self.assertEqual(self.values(builds, "2020-06-01"), [])
        self.assertEqual(self.values(builds, "2021-06-01"), ["C"])

    def test_true_from_is_effective_then_published_date_in_utc(self):
        self.assertEqual(page_true_from({"Effective": "2025-09-01"}, "2025-01-01T00:00:00+00:00"), "2025-09-01")
        self.assertEqual(page_true_from({"Effective": "2025-02-30"}, "2025-01-01T23:30:00-02:00"), "2025-01-02")
        self.assertIsNone(page_true_from({}, None))


class EvidenceTests(unittest.TestCase):
    def test_executive_candidates_are_per_title(self):
        evidence = Evidence("acme-robotics.test")
        evidence.add_page("https://acme-robotics.test/team", "nimble",
                          "Effective: 2025-09-01\n\nAna Silva is the chief financial officer of Acme Robotics.\n"
                          "Acme Robotics CTO: Ben Okafor.\nAcme Robotics CEO: Dana Ruiz.")
        [page_] = evidence.pages()
        self.assertEqual(sorted((s, c.value) for s, c in page_.candidates),
                         [("ceo", "Dana Ruiz"), ("cfo", "Ana Silva"), ("cto", "Ben Okafor")])
        self.assertEqual(page_.true_from, "2025-09-01")

    def test_title_phrases_are_their_own(self):
        self.assertEqual(supported_value("coo", "Acme Robotics COO: Eva Lund.", "acme-robotics.test"), "Eva Lund")
        self.assertIsNone(supported_value("cfo", "Acme Robotics COO: Eva Lund.", "acme-robotics.test"))


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.s = ScriptedStore()
        self.store = self.s.store

    def history(self, field):
        return self.store.history("acme.test")["fields"][field]

    def test_first_build_gives_initial_entries_and_no_feed(self):
        self.s.build([page("u", "2021-04-01", ceo="Dana Ruiz")])
        self.assertEqual([e["type"] for e in self.history("ceo")], ["initial"])
        self.assertEqual(self.history("ceo")[0]["true_from"], "2021-04-01")
        self.assertEqual(self.history("hq_city"), [])
        self.assertEqual(self.store.changes(0, 50), {"changes": [], "has_more": False})
        ceo = self.store.get_dossier("acme.test")["fields"]["ceo"]
        self.assertEqual((ceo["true_from"], ceo["learned_at"]), ("2021-04-01", T0))

    def test_change_correction_and_same_value(self):
        self.s.build([page("u", "2021-04-01", ceo="Dana Ruiz")])
        self.s.build([page("u", "2026-03-20", ceo="Lee Park")], "2026-04-01T09:00:00+00:00")
        self.s.build([page("u", "2026-03-20", ceo="Lee Park", hq_city="Lisbon")], "2026-05-01T09:00:00+00:00")
        self.s.build([page("u", "2026-03-10", ceo="Sam Ortiz")], "2026-06-01T09:00:00+00:00")
        entries = self.store.changes(0, 50)["changes"]
        self.assertEqual([(e["seq"], e["field"], e["type"], e["from"], e["to"]) for e in entries],
                         [(1, "ceo", "change", "Dana Ruiz", "Lee Park"),
                          (2, "hq_city", "change", None, "Lisbon"),
                          (3, "hq_city", "change", "Lisbon", None),
                          (4, "ceo", "correction", "Lee Park", "Sam Ortiz")])
        self.assertEqual(entries[0]["learned_at"], "2026-04-01T09:00:00+00:00")
        self.assertEqual([e["type"] for e in self.history("ceo")], ["initial", "change", "correction"])
        self.assertEqual(self.store.changes(2, 1), {"changes": entries[2:3], "has_more": True})

    def test_disappearing_value_leaves_an_unknown_field_without_times(self):
        self.s.build([page("u", "2021-04-01", ceo="Dana Ruiz")])
        self.s.build([PageVersion("u", "2021-04-02", ())], "2026-04-01T09:00:00+00:00")
        ceo = self.store.get_dossier("acme.test")["fields"]["ceo"]
        self.assertEqual((ceo["status"], ceo["true_from"], ceo["learned_at"]), ("unknown", None, None))
        self.assertEqual(self.history("ceo")[-1], {"type": "change", "value": None, "true_from": None,
                                                   "learned_at": "2026-04-01T09:00:00+00:00", "citations": []})

    def test_failed_build_adds_nothing(self):
        self.s.build([page("u", "2021-04-01", ceo="Dana Ruiz")])
        self.s.build(None, "2026-04-01T09:00:00+00:00")
        self.assertEqual(self.store.get_dossier("acme.test")["state"], "failed")
        self.assertEqual(self.store.changes(0, 50)["changes"], [])
        self.assertEqual(len(self.history("ceo")), 1)

    def test_as_of_uses_learned_at_and_ties_go_to_the_last_build(self):
        self.s.build([page("u", "2021-04-01", ceo="Dana Ruiz")])
        self.s.build([page("u", "2020-01-01", ceo="Lee Park")])          # same clock time
        self.s.build([page("u", "2020-01-01", ceo="Sam Ortiz")], "2026-04-01T09:00:00+00:00")
        at = lambda text: self.store.get_dossier("acme.test", parse_timestamp(text))     # noqa: E731
        self.assertEqual(at("2026-03-01T12:00:00+03:00")["fields"]["ceo"]["value"], "Lee Park")   # 09:00Z
        self.assertEqual(at("2026-03-15T00:00:00+00:00")["spent_units"], 10)
        self.assertEqual(at("2026-04-01T09:00:00Z")["fields"]["ceo"]["value"], "Sam Ortiz")
        with self.assertRaises(ApiError) as caught:
            at("2026-03-01T08:59:59+00:00")
        self.assertEqual(caught.exception.status, 404)

    def test_values_at_true_date(self):
        self.s.build([page("u", "2021-04-01", ceo="Dana Ruiz")])
        self.s.build([page("u", "2026-03-20", ceo="Lee Park")], "2026-04-01T09:00:00+00:00")
        values = lambda true_at, as_of=None: self.store.values_at(          # noqa: E731
            "acme.test", true_at, parse_timestamp(as_of) if as_of else None, as_of)["fields"]
        self.assertEqual(values("2025-06-01")["ceo"]["value"], "Dana Ruiz")
        self.assertEqual(values("2026-03-20")["ceo"]["value"], "Lee Park")
        self.assertEqual(values("2020-01-01")["ceo"], {"value": None, "true_from": None, "citations": []})
        self.assertEqual(values("2026-03-25", "2026-03-15T00:00:00+00:00")["ceo"]["value"], "Dana Ruiz")
        self.assertIsNone(values("2026-03-25")["executives"]["value"])

    def test_executives_value_members_and_corrections(self):
        self.s.build([page("t", "2025-09-01", cfo="Ana Silva", cto="Ben Okafor")])
        executives = self.store.get_dossier("acme.test")["fields"]["executives"]
        self.assertEqual(executives["value"], [{"title": "cfo", "name": "Ana Silva"},
                                               {"title": "cto", "name": "Ben Okafor"}])
        self.assertEqual((executives["status"], executives["true_from"]), ("known", "2025-09-01"))
        self.assertEqual([c["title"] for c in executives["candidates"]], ["cfo", "cto"])
        self.s.build([page("t", "2025-08-01", cfo="Ana Silva", cto="Eva Lund")], "2026-04-01T09:00:00+00:00")
        self.s.build([page("t", "2025-07-01", cfo="Ana Silva", cto="Eva Lund", coo="Ola Berg")],
                     "2026-05-01T09:00:00+00:00")
        self.assertEqual([(e["field"], e["type"]) for e in self.store.changes(0, 50)["changes"]],
                         [("executives", "correction"), ("executives", "change")])

    def test_history_survives_export_and_import(self):
        self.s.build([page("u", "2021-04-01", ceo="Dana Ruiz")])
        self.s.build([page("u", "2026-03-20", ceo="Lee Park")], "2026-04-01T09:00:00+00:00")
        document = self.store.export_state()
        other = ScriptedStore()
        other.store.import_state(document)
        self.assertEqual(other.store.export_state(), document)
        as_of = parse_timestamp("2026-03-15T00:00:00+00:00")
        self.assertEqual(other.store.get_dossier("acme.test", as_of), self.store.get_dossier("acme.test", as_of))
        other.build([page("u", "2026-05-01", ceo="Sam Ortiz")], "2026-05-01T09:00:00+00:00")
        self.assertEqual([e["seq"] for e in other.store.changes(0, 50)["changes"]], [1, 2])


class UpgradeTests(unittest.TestCase):
    STATE = {"users": [], "tokens": {}, "idempotency": [], "dossier_counter": 1}

    def import_one(self, fields, researched="2026-03-01T09:00:00+00:00"):
        s = ScriptedStore()
        document = {"track": "dossier", "format_version": 1, "state": {**self.STATE, "dossiers": [{
            "dossier_id": "d_1", "domain": "acme.test", "state": "ready", "researched_at": researched,
            "spent_units": 12, "fields": fields}]}}
        s.store.import_state(document)
        return s

    def stage_one_fields(self):
        unknown = {"value": None, "status": "unknown", "citations": []}
        fields = {name: unknown for name in ("legal_name", "hq_city", "founded_year", "headcount_range", "funding_total")}
        fields["ceo"] = {"value": "Dana Ruiz", "status": "known", "citations": [
            {"url": "https://acme.test/a", "excerpt": "Acme CEO: Dana Ruiz.", "provider": "nimble"}]}
        return fields

    def test_stage_one_import_is_one_ready_build(self):
        s = self.import_one(self.stage_one_fields())
        history = s.store.history("acme.test")["fields"]
        self.assertEqual([(e["type"], e["true_from"], e["learned_at"]) for e in history["ceo"]],
                         [("initial", None, T0)])
        self.assertEqual(history["executives"], [])
        ceo = s.store.get_dossier("acme.test", parse_timestamp(T0))["fields"]["ceo"]
        self.assertEqual((ceo["learned_at"], ceo["candidates"][0]["learned_at"]), (T0, T0))
        with self.assertRaises(ApiError):
            s.store.get_dossier("acme.test", parse_timestamp("2026-02-28T00:00:00+00:00"))
        self.assertEqual(s.store.changes(0, 50)["changes"], [])
        s.build([page("u", "2026-03-20", ceo="Lee Park", cfo="Ana Silva")], "2026-04-01T09:00:00+00:00")
        self.assertEqual([(e["field"], e["type"]) for e in s.store.changes(0, 50)["changes"]],
                         [("ceo", "change"), ("executives", "change")])

    def test_stage_two_import_takes_true_from_from_published_date(self):
        fields = self.stage_one_fields()
        fields["ceo"]["candidates"] = [{"value": "Dana Ruiz", "url": "https://acme.test/a", "excerpt": "Acme CEO: Dana Ruiz.",
                                        "provider": "nimble", "kind": "own", "published_at": "2026-01-10T00:00:00+00:00",
                                        "retrieved_at": T0, "selected": True}]
        for name in fields:
            fields[name].setdefault("candidates", [])
        s = self.import_one(fields)
        ceo = s.store.get_dossier("acme.test")["fields"]["ceo"]
        self.assertEqual((ceo["true_from"], ceo["candidates"][0]["true_from"]), ("2026-01-10", "2026-01-10"))
        self.assertEqual(s.store.history("acme.test")["fields"]["ceo"][0]["true_from"], "2026-01-10")

    def test_never_researched_dossier_has_no_as_of(self):
        s = self.import_one({name: {"value": None, "status": "unknown", "citations": []}
                             for name in self.stage_one_fields()}, researched=None)
        with self.assertRaises(ApiError):
            s.store.get_dossier("acme.test", parse_timestamp("2030-01-01T00:00:00+00:00"))
        s.build([page("u", "2026-03-20", ceo="Lee Park")], "2026-04-01T09:00:00+00:00")
        self.assertEqual([e["type"] for e in s.store.history("acme.test")["fields"]["ceo"]], ["initial"])


class DurabilityTests(unittest.TestCase):
    def test_state_and_clock_survive_a_restart_and_seq_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.journal")
            first = ScriptedStore(Journal(path))
            session = first.store.signup("a@example.com", "correct horse", "Ada")
            first.build([page("u", "2021-04-01", ceo="Dana Ruiz")])
            first.build([page("u", "2026-03-20", ceo="Lee Park")], "2026-04-01T09:00:00+00:00")
            first.store.idempotent("u_1", "POST", "/dossiers", "k", "x", lambda: (202, {"state": "building"}))
            before = first.store.export_state()
            reloaded = Store(lambda *a: None, Journal(path))
            self.assertEqual(reloaded.export_state(), before)
            self.assertEqual(reloaded.authenticate(session["token"]), session["user_id"])
            self.assertEqual(reloaded.clock.now(), datetime(2026, 4, 1, 9, tzinfo=timezone.utc))
            self.assertEqual(reloaded.idempotent("u_1", "POST", "/dossiers", "k", "x", lambda: (500, {})),
                             (200, {"state": "building"}))

    def test_torn_last_line_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.journal")
            first = ScriptedStore(Journal(path))
            first.store.signup("a@example.com", "correct horse", "Ada")
            expected = first.store.export_state()
            with open(path, "ab") as handle:
                handle.write(b'{"records":[["user",{"id":"u_x"')
            self.assertEqual(Store(lambda *a: None, Journal(path)).export_state(), expected)


if __name__ == "__main__":
    unittest.main()
