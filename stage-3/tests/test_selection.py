import unittest

from dossier_service.evidence import Evidence, page_kind, published_at
from dossier_service.selection import Candidate, field_of

NEW = "2026-02-20T00:00:00+00:00"
OLD = "2026-01-10T00:00:00+00:00"


def cand(value, url="https://a.test/x", kind="own", published=OLD, provider="nimble"):
    return Candidate(value, url, f"excerpt {value}", provider, kind, published, "2026-03-01T09:00:00+00:00")


def values(field):
    return [c["value"] for c in field["candidates"]]


class SelectionTests(unittest.TestCase):
    def test_no_candidate_is_unknown(self):
        self.assertEqual(field_of([]), {"value": None, "status": "unknown", "true_from": None, "learned_at": None,
                                         "citations": [], "candidates": []})

    def test_authority_outranks_recency(self):
        field = field_of([cand("Sam", kind="aggregator", published=NEW), cand("Dana", kind="own", published=OLD),
                          cand("Lee", kind="news", published=NEW)])
        self.assertEqual(values(field), ["Dana", "Lee", "Sam"])
        self.assertEqual((field["value"], field["status"]), ("Dana", "contested"))
        self.assertEqual([c["selected"] for c in field["candidates"]], [True, False, False])

    def test_own_and_filing_rank_equal_then_recency(self):
        field = field_of([cand("A", kind="own", published=OLD), cand("B", kind="filing", published=NEW)])
        self.assertEqual(values(field), ["B", "A"])

    def test_missing_publication_time_ranks_last_within_authority(self):
        field = field_of([cand("A", published=None, url="https://a.test/1"), cand("B", published=OLD, url="https://z.test/1")])
        self.assertEqual(values(field), ["B", "A"])

    def test_equal_instants_in_different_offsets_tie_on_url(self):
        field = field_of([cand("B", published="2026-01-10T02:00:00+02:00", url="https://b.test"),
                          cand("A", published=OLD, url="https://a.test")])
        self.assertEqual(values(field), ["A", "B"])

    def test_url_then_provider_then_value(self):
        field = field_of([cand("B", provider="tavily"), cand("C", provider="nimble"), cand("A", provider="nimble")])
        self.assertEqual(values(field), ["A", "C", "B"])
        numbers = field_of([cand(10), cand(9), cand(100)])
        self.assertEqual(values(numbers), [9, 10, 100])

    def test_imported_candidate_has_aggregator_authority(self):
        field = field_of([cand("I", kind=None, published=None), cand("N", kind="news", published=None)])
        self.assertEqual(values(field), ["N", "I"])

    def test_same_value_is_known_with_every_citation_in_rank_order(self):
        field = field_of([cand("Dana", url="https://b.test"), cand(" Dana ", url="https://a.test")])
        self.assertEqual(field["status"], "known")
        self.assertEqual([c["url"] for c in field["citations"]], ["https://a.test", "https://b.test"])
        self.assertEqual(field["value"], "Dana")

    def test_citations_hold_only_the_selected_value(self):
        field = field_of([cand("Dana", url="https://a.test"), cand("Sam", url="https://b.test"),
                          cand("Dana", url="https://c.test")])
        self.assertEqual([c["url"] for c in field["citations"]], ["https://a.test", "https://c.test"])


class EvidenceTests(unittest.TestCase):
    def test_kind_and_publication_from_header(self):
        text = "Kind: news\nPublished: 2026-02-20T00:00:00Z\n\nAcme Robotics CEO: Sam Ortiz.\nAcme Robotics CEO: Sam Ortiz."
        evidence = Evidence("acme-robotics.test")
        evidence.add_page("https://wire.test/x", "nimble", text)
        [page] = evidence.pages()
        [(slot, candidate)] = page.candidates
        self.assertEqual((slot, candidate.value, candidate.kind, candidate.published_at, candidate.true_from),
                         ("ceo", "Sam Ortiz", "news", NEW, "2026-02-20"))
        self.assertEqual(page.true_from, "2026-02-20")

    def test_page_kind_falls_back_to_host(self):
        self.assertEqual(page_kind({}, "https://www.acme.test/about", "acme.test"), "own")
        self.assertEqual(page_kind({"Kind": "blog"}, "https://acme.test.evil.test/", "acme.test"), "aggregator")
        self.assertEqual(page_kind({"Kind": "filing"}, "https://x.test", "acme.test"), "filing")

    def test_bad_publication_time_is_none(self):
        self.assertIsNone(published_at({"Published": "2026-02-20"}))
        self.assertIsNone(published_at({}))

    def test_one_candidate_per_page_and_value(self):
        text = "\nAcme Robotics was founded in 2014. Founded in 2014, Acme Robotics is small. Acme Robotics was founded in 2015."
        evidence = Evidence("acme-robotics.test")
        evidence.add_page("https://a.test/", "nimble", text)
        [page] = evidence.pages()
        self.assertEqual([c.value for slot, c in page.candidates if slot == "founded_year"], [2014, 2015])


if __name__ == "__main__":
    unittest.main()
