"""Evidence a build gathers, and the decision of which value each field holds."""
from __future__ import annotations

from dataclasses import dataclass

from .pages import Page, citable_sentences, parse_served_text
from .support import FIELDS, collapse_whitespace, supported_value

MAX_CITATIONS = 3
SETTLED_SCORE = 3.0
_KIND_WEIGHT = {"own": 3.0, "filing": 3.0, "news": 2.0, "aggregator": 1.0}
_UNKNOWN_KIND_WEIGHT = 1.5
_CLAIM_BONUS = 0.5


@dataclass(frozen=True)
class Candidate:
    field: str
    value: object
    url: str
    excerpt: str
    provider: str


class Evidence:
    """Pages and candidate citations for one company, built up over one build."""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self.pages: dict[str, Page] = {}
        self.candidates: dict[str, list[Candidate]] = {f: [] for f in FIELDS}
        self.claims: dict[str, object] = {}
        self._seen: set[tuple[str, str, str]] = set()
        self._excerpts: dict[tuple[str, str], str] = {}

    def page(self, url: str) -> Page:
        return self.pages.setdefault(url, Page(url))

    def add_text(self, url: str, provider: str, text: str, *, full: bool, cut_short: bool,
                 title: str = "") -> None:
        """Record text a provider served for ``url`` and harvest the sentences that support a value."""
        self.page(url).add(text, full, title)
        served_prose = collapse_whitespace(parse_served_text(text).prose)
        for sentence in citable_sentences(text, cut_short):
            self._harvest(url, provider, sentence, served_prose)

    def add_research_excerpt(self, url: str, field: str, claimed: object, excerpt: str) -> None:
        """Record an excerpt a research run cited; the claim only breaks ties between values."""
        self.page(url)
        for sentence in citable_sentences(excerpt, cut_short=False):
            self._harvest(url, "nimble", sentence, sentence)
            if claimed is not None and field in FIELDS:
                self.claims.setdefault(field, claimed)

    def _harvest(self, url: str, provider: str, sentence: str, served_prose: str) -> None:
        for field in FIELDS:
            value = supported_value(field, sentence, self.domain)
            key = (url, sentence, field)
            if value is None or key in self._seen or sentence not in served_prose:
                continue
            self._seen.add(key)
            self.candidates[field].append(Candidate(field, value, url, sentence, provider))

    # ------------------------------------------------------------ source quality

    def weight(self, url: str) -> float:
        """How far to trust a page: the company's own site and registry filings most, aggregators least.

        A page that calls itself ``own`` but is registered to someone else (a parked or
        look-alike site) is worth no more than an aggregator.
        """
        page = self.pages[url]
        host_is_company = page.host == self.domain or page.host.endswith("." + self.domain)
        registrant = page.header.get("Registrant", "").lower()
        if page.kind == "own":
            return _KIND_WEIGHT["own"] if host_is_company or registrant == self.domain else _KIND_WEIGHT["aggregator"]
        if page.kind in _KIND_WEIGHT:
            return _KIND_WEIGHT[page.kind]
        return _KIND_WEIGHT["own"] if host_is_company else _UNKNOWN_KIND_WEIGHT

    def _date(self, url: str) -> str:
        header = self.pages[url].header
        return header.get("Published") or header.get("Effective") or ""

    # ------------------------------------------------------------ decisions

    def _scores(self, field: str) -> dict[object, tuple[float, str]]:
        """Per value: the summed weight of its independent origins, and its newest source date."""
        per_origin: dict[object, dict[str, float]] = {}
        newest: dict[object, str] = {}
        for cand in self.candidates[field]:
            origins = per_origin.setdefault(cand.value, {})
            origin = self.pages[cand.url].origin()
            origins[origin] = max(origins.get(origin, 0.0), self.weight(cand.url))
            newest[cand.value] = max(newest.get(cand.value, ""), self._date(cand.url))
        scores = {}
        for value, origins in per_origin.items():
            bonus = _CLAIM_BONUS if self.claims.get(field) == value else 0.0
            scores[value] = (sum(origins.values()) + bonus, newest[value])
        return scores

    def best(self, field: str):
        """The value the evidence best supports for ``field``, else None."""
        scores = self._scores(field)
        return max(scores, key=lambda v: scores[v]) if scores else None

    def score(self, field: str) -> float:
        scores = self._scores(field)
        return max(scores.values())[0] if scores else 0.0

    def is_settled(self, field: str) -> bool:
        return self.score(field) >= SETTLED_SCORE

    def unknown_fields(self) -> list[str]:
        return [f for f in FIELDS if not self.candidates[f]]

    def unsettled_fields(self) -> list[str]:
        return [f for f in FIELDS if not self.is_settled(f)]

    def field_result(self, field: str) -> dict:
        """The API shape of one field: value, status and the citations that support it."""
        value = self.best(field)
        if value is None:
            return {"value": None, "status": "unknown", "citations": []}
        chosen = [c for c in self.candidates[field] if c.value == value]
        chosen.sort(key=lambda c: self._date(c.url), reverse=True)
        chosen.sort(key=lambda c: -self.weight(c.url))
        citations, origins = [], set()
        for cand in chosen:
            origin = self.pages[cand.url].origin()
            if origin in origins and len(citations) >= 1:
                continue
            origins.add(origin)
            citations.append({"url": cand.url, "excerpt": cand.excerpt, "provider": cand.provider})
            if len(citations) == MAX_CITATIONS:
                break
        return {"value": value, "status": "known", "citations": citations}

    def results(self) -> dict[str, dict]:
        return {f: self.field_result(f) for f in FIELDS}
