"""One build: gather pages through the provider, read their browser text, collect the candidates.

The plan spends the 80 units where they buy the most. Searches only name pages, so they are the
cheap ``lite`` kind (1 unit): one on the bare domain and one per field. A research run (25 units)
names the pages its claims cite, some of which no search returns. Page text is read only from
Nimble's rendered extract (3 units a page): it is the text a browser shows, which can differ
from the text a search or a plain extract serves. What is left of the budget after the searches
and the research run reads as many pages as it pays for, the likeliest first.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlparse

from .domains import company_name, normalise_domain
from .evidence import Evidence
from .gateway import RENDERED_EXTRACT_COST, BuildStopped, CallFailed, Gateway, SearchHit
from .ledger import BudgetExhausted
from .pages import citable_sentences, parse_served_text
from .selection import Candidate
from .support import FIELDS, supported_value

log = logging.getLogger("dossier.builder")

FIELD_QUERIES = {
    "legal_name": "legal name registered name legal entity",
    "hq_city": "headquartered in headquarters head office based in registered office",
    "ceo": "chief executive officer CEO chief executive",
    "founded_year": "founded established incorporated founding",
    "headcount_range": "employees headcount staff people workforce",
    "funding_total": "raised funding investment invested",
}
_SEPARATORS = re.compile(r"[-_./]+")


@dataclass(frozen=True)
class BuildResult:
    candidates: dict[str, list[Candidate]]
    succeeded: bool             # some provider call was answered


class Builder:
    def __init__(self, domain: str, gateway: Gateway, pool: ThreadPoolExecutor) -> None:
        self._domain = domain
        self._gateway = gateway
        self._pool = pool
        self._evidence = Evidence(domain)

    def run(self) -> BuildResult:
        try:
            hits, cited = self._discover()
            self._read(self._reading_order(hits, cited))
        except (BuildStopped, BudgetExhausted):
            pass
        return BuildResult(self._evidence.candidates(), self._gateway.successes > 0)

    # ---------------------------------------------------------------- discovery

    def _discover(self) -> tuple[dict[str, list[tuple[int, SearchHit]]], list[str]]:
        """Run every search and the research run together: the pages found, with their ranks, and the cited ones."""
        queries = [self._domain, *(f"{self._domain} {FIELD_QUERIES[field]}" for field in FIELDS)]
        calls = [lambda q=query: self._gateway.search(q) for query in queries]
        if self._gateway.can_research():
            calls.append(self._research)
        outcomes = self._fan_out(calls)
        found: dict[str, list[tuple[int, SearchHit]]] = {}
        for hits in outcomes[:len(queries)]:
            for rank, hit in enumerate(hits or []):
                found.setdefault(hit.url, []).append((rank, hit))
        cited = outcomes[len(queries)] if len(outcomes) > len(queries) else None
        return found, cited or []

    def _research(self) -> list[str]:
        return self._gateway.research(
            f"Research the company with the web domain {self._domain}: its legal name, "
            "headquarters city, chief executive, founding year, headcount and total funding raised.")

    # ---------------------------------------------------------------- reading

    def _reading_order(self, found: dict[str, list[tuple[int, SearchHit]]], cited: list[str]) -> list[str]:
        """Pages to read, best first: those research cites, then those most likely to state facts about the company."""
        ordered = list(cited)
        rest = sorted((url for url in found if url not in cited), key=lambda url: -self._likelihood(found[url]))
        return ordered + rest

    def _likelihood(self, appearances: list[tuple[int, SearchHit]]) -> float:
        """How likely a page found by search is to state a fact about the company, judged from what search showed."""
        hit = appearances[0][1]
        host = normalise_domain(urlparse(hit.url).hostname or "")
        name = company_name(self._domain)
        shown = _SEPARATORS.sub(" ", f"{hit.url} {hit.title}").lower()
        score = 0.0
        if host == self._domain:
            score += 3.0
        if name.lower() in shown or self._domain in hit.url.lower():
            score += 2.0
        if any(supported_value(field, sentence, self._domain) is not None
               for sentence in citable_sentences(parse_served_text(hit.text).prose) for field in FIELDS):
            score += 2.0
        score += sum(1.0 - 0.05 * rank for rank, _ in appearances)
        return score

    def _read(self, urls: list[str]) -> None:
        affordable = self._gateway.budget_left() // RENDERED_EXTRACT_COST
        batch = urls[:affordable]
        texts = self._fan_out([lambda u=url: self._gateway.extract_rendered(u) for url in batch])
        for url, text in zip(batch, texts):
            if text:
                self._evidence.add_page(url, "nimble", text)

    # ---------------------------------------------------------------- helpers

    def _fan_out(self, calls) -> list:
        """Run provider calls concurrently; a call that failed or was stopped yields None."""
        def guarded(call):
            try:
                return call()
            except (CallFailed, BuildStopped, BudgetExhausted) as failure:
                log.info("call skipped: %r", failure)
                return None

        return list(self._pool.map(guarded, calls))
