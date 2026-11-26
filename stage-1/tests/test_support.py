import unittest

from dossier_service.domains import parse_domain
from dossier_service.pages import citable_sentences, parse_served_text
from dossier_service.support import is_single_sentence, split_sentences, supported_value

DOMAIN = "acme-robotics.test"


class SupportTests(unittest.TestCase):
    def test_spec_examples(self):
        cases = [
            ("ceo", "Dana Ruiz has led Acme Robotics as chief executive since 2021.", "Dana Ruiz"),
            ("ceo", "Acme Robotics CEO: Sam Ortiz.", "Sam Ortiz"),
            ("founded_year", "Acme Robotics was founded in 2014.", 2014),
            ("headcount_range", "Acme Robotics employs about 120 people.", "51-200"),
            ("funding_total", "Acme Robotics has raised $12M.", 12_000_000),
            ("funding_total", "Acme Robotics has raised 12 million dollars.", 12_000_000),
            ("funding_total", "Acme Robotics has raised US$12.5 million.", 12_500_000),
            ("funding_total", "Acme Robotics has raised 12,000,000 US dollars.", 12_000_000),
            ("legal_name", "The legal name of Acme Robotics is Acme Robotics, Inc.", "Acme Robotics, Inc."),
            ("hq_city", "Acme Robotics is headquartered in Lisbon, Portugal.", "Lisbon"),
            ("headcount_range", "Acme Robotics has 51-200 employees.", "51-200"),
        ]
        for field, excerpt, value in cases:
            with self.subTest(excerpt=excerpt):
                self.assertEqual(supported_value(field, excerpt, DOMAIN), value)

    def test_nothing_supported(self):
        cases = [
            ("funding_total", "Acme Robotics is reportedly in talks to raise $40M."),
            ("hq_city", "Acme Robotics opened a sales office in Porto."),
            ("headcount_range", "Acme Robotics has 50-200 employees."),
            ("founded_year", "Acme Robotics was founded in 2014 and again in 2016."),
            ("funding_total", "Acme Robotics has raised EUR 12 million."),
            ("ceo", "Dana Ruiz is the CEO."),
            ("ceo", "Dana Ruiz succeeded Sam Ortiz as CEO of Acme Robotics."),
            ("founded_year", "Acme Robotics was founded in 2014. It is not small."),
        ]
        for field, excerpt in cases:
            with self.subTest(excerpt=excerpt):
                self.assertIsNone(supported_value(field, excerpt, DOMAIN))

    def test_sentence_splitting(self):
        self.assertEqual(split_sentences("Acme Robotics, Inc. is based in Lisbon. It grows!\nNew line"),
                         ["Acme Robotics, Inc. is based in Lisbon.", "It grows!", "New line"])
        self.assertTrue(is_single_sentence("Acme Robotics, Inc. is based in Lisbon."))
        self.assertFalse(is_single_sentence("One. Two."))

    def test_header_is_not_prose(self):
        text = "Kind: own\nFacts: {\"ceo\": \"Dana Ruiz\"}\n\nAcme Robotics CEO: Sam Ortiz."
        self.assertEqual(parse_served_text(text).header["Kind"], "own")
        self.assertEqual(citable_sentences(text, cut_short=False), ["Acme Robotics CEO: Sam Ortiz."])

    def test_cut_short_text_drops_unterminated_tail(self):
        text = "Acme Robotics was founded in 2014. Acme Robotics employs about 12"
        self.assertEqual(citable_sentences(text, cut_short=True), ["Acme Robotics was founded in 2014."])

    def test_domain_normalisation(self):
        self.assertEqual(parse_domain(" WWW.Acme-Robotics.TEST. "), "acme-robotics.test")
        for bad in ("https://acme.test", "acme", "a..test", "-a.test", "a.test/x", ""):
            self.assertIsNone(parse_domain(bad), bad)


if __name__ == "__main__":
    unittest.main()
