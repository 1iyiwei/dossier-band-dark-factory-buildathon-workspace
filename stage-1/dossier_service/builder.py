"""One build: gather evidence through the provider, then decide each field.

The plan spends units where they buy the most. Search is cheap, so the build
searches first (the required one for the bare domain, then one cheap search per field
still short of authoritative support) and reads the snippets it is served. It pays for a full
page (extract, 1 unit) only where a snippet was cut short, and for a research run (25 units)
only when some field still has no support at all. It stops as soon as every field is
supported by an authoritative page.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .evidence import Evidence
from .gateway import BuildStopped, CallFailed, Gateway, SearchHit
from .ledger import BudgetExhausted

log = logging.getLogger("dossier.builder")

FIELD_QUERIES = {
    "legal_name": "legal name registered name legal entity",
    "hq_city": "headquartered in headquarters head office based in registered office",
    "ceo": "chief executive officer CEO chief executive",
    "founded_year": "founded established incorporated founding",
    "headcount_range": "employees headcount staff people workforce",
    "funding_total": "raised funding investment invested",
}
LITE_COMPLETE_BELOW = 280       # a lite snippet is cut at 300 characters
FAST_COMPLETE_BELOW = 1400      # a fast result is cut at 1500 characters
EXTRACT_WAVE = 8
EXTRACT_UNITS_BEFORE_RESEARCH = 16
EXTRACT_UNITS_TOTAL = 40
_RANK_WEIGHT = 0.1


@dataclass(frozen=True)
class BuildResult:
    fields: dict[str, dict]
    succeeded: bool             # some provider call was answered


class Builder:
    def __init__(self, domain: str, gateway: Gateway, pool: ThreadPoolExecutor) -> None:
        self._domain = domain
        self._gateway = gateway
        self._pool = pool
        self._evidence = Evidence(domain)
        self._ranks: dict[str, dict[str, int]] = {}
        self._tried: set[str] = set()
        self._extract_units = 0

    def run(self) -> BuildResult:
        try:
            self._search_domain()
            if self._evidence.unsettled_fields():
                self._search_fields()
            self._extract_pages(EXTRACT_UNITS_BEFORE_RESEARCH)
            if self._evidence.unknown_fields():
                self._research()
            self._extract_pages(EXTRACT_UNITS_TOTAL)
        except (BuildStopped, BudgetExhausted):
            pass
        return BuildResult(self._evidence.results(), self._gateway.successes > 0)

    # ---------------------------------------------------------------- searches

    def _search_domain(self) -> None:
        """The one search whose query is exactly the normalised domain."""
        try:
            self._ingest("domain", "fast", self._gateway.search(self._domain, "fast"))
        except CallFailed as failure:
            log.info("domain search failed: %s", failure)

    def _search_fields(self) -> None:
        tags = self._evidence.unsettled_fields()
        outcomes = self._fan_out(
            [lambda t=tag: self._gateway.search(f"{self._domain} {FIELD_QUERIES[t]}", "lite") for tag in tags])
        for tag, hits in zip(tags, outcomes):
            if hits is not None:
                self._ingest(tag, "lite", hits)

    def _ingest(self, tag: str, depth: str, hits: list[SearchHit]) -> None:
        limit = LITE_COMPLETE_BELOW if depth == "lite" else FAST_COMPLETE_BELOW
        for rank, hit in enumerate(hits):
            full = len(hit.text) < limit
            self._evidence.add_text(hit.url, "nimble", hit.text, full=full, cut_short=not full, title=hit.title)
            self._ranks.setdefault(hit.url, {})[tag] = rank

    # ---------------------------------------------------------------- extracts

    def _candidates(self) -> list[str]:
        """Pages known only in part, best first for the fields still short of support."""
        wanted = {"domain", *self._evidence.unsettled_fields()}
        pending = [url for url, page in self._evidence.pages.items()
                   if not page.full and url not in self._tried and url in self._ranks]

        def score(url: str) -> float:
            seen = sum(1 - _RANK_WEIGHT * rank for tag, rank in self._ranks[url].items() if tag in wanted)
            return seen + (0.5 if self._evidence.weight(url) >= 3.0 else 0.0)

        return sorted((u for u in pending if score(u) > 0), key=score, reverse=True)

    def _extract_pages(self, unit_cap: int) -> None:
        while self._evidence.unsettled_fields() and self._extract_units < unit_cap:
            batch = self._candidates()[:min(EXTRACT_WAVE, unit_cap - self._extract_units)]
            if not batch:
                return
            self._tried.update(batch)
            self._extract_units += len(batch)
            texts = self._fan_out([lambda u=url: self._gateway.extract(u) for url in batch])
            for url, text in zip(batch, texts):
                if text:
                    self._evidence.add_text(url, "nimble", text, full=True, cut_short=False)

    # ---------------------------------------------------------------- research

    def _research(self) -> None:
        if not self._gateway.can_research():
            return
        query = (f"Research the company with the web domain {self._domain}: its legal name, "
                 "headquarters city, chief executive, founding year, headcount and total funding raised.")
        try:
            claims, citations = self._gateway.research(query)
        except CallFailed as failure:
            log.info("research failed: %s", failure)
            return
        for citation in citations:
            for excerpt in citation.excerpts:
                self._evidence.add_research_excerpt(citation.url, citation.field, claims.get(citation.field), excerpt)

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

