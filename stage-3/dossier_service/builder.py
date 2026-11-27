"""One build: gather pages through the provider, read their browser text, collect the candidates.

The plan spends the 80 units where they buy the most. Searches only name pages, so they are the
cheap ``lite`` kind (1 unit): one on the bare domain and one per field. A research run (25 units)
names the pages its claims cite, some of which no search returns. Page text is read only from
Nimble's rendered extract (3 units a page): it is the text a browser shows, which can differ
from the text a search or a plain extract serves. What is left of the budget after the searches
and the research run reads as many pages as it pays for, the likeliest first. A page whose URL,
title and snippet never name the company is first checked with a plain extract (1 unit) and is
rendered only when the text it serves names the company: a page that never names it states
nothing about it. When the providers are slow there is no time for that check and every page is
rendered, so reading is one round of parallel calls after discovery.
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
from .support import SLOTS, names_company, supported_value
from .versions import PageVersion

log = logging.getLogger("dossier.builder")

FIELD_QUERIES = {
    "legal_name": "legal name registered name legal entity",
    "hq_city": "headquartered in headquarters head office based in registered office",
    "ceo": "chief executive officer CEO chief executive",
    "founded_year": "founded established incorporated founding",
    "headcount_range": "employees headcount staff people workforce",
    "funding_total": "raised funding investment invested",
    "executives": "chief financial officer CFO chief operating officer COO chief technology officer CTO",
}
_SEPARATORS = re.compile(r"[-_./]+")
PREFILTER_SHARE = 0.3          # at most this share of the budget left after discovery checks doubtful pages
MENTION_BONUS = 2.0


@dataclass(frozen=True)
class BuildResult:
    pages: list[PageVersion]    # every page the build read, with what its text supports
    succeeded: bool             # some provider call was answered


class Builder:
    def __init__(self, domain: str, gateway: Gateway, pool: ThreadPoolExecutor) -> None:
        self._domain = domain
        self._gateway = gateway
        self._pool = pool
        self._evidence = Evidence(domain)

    def run(self) -> BuildResult:
        try:
            found, cited = self._discover()
            self._read(found, cited)
        except (BuildStopped, BudgetExhausted):
            pass
        return BuildResult(self._evidence.pages(), self._gateway.successes > 0)

    # ---------------------------------------------------------------- discovery

    def _discover(self) -> tuple[dict[str, list[tuple[int, SearchHit]]], list[str]]:
        """Run every search and the research run together: the pages found, with their ranks, and the cited ones."""
        queries = [self._domain, *(f"{self._domain} {query}" for query in FIELD_QUERIES.values())]
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

    def _read(self, found: dict[str, list[tuple[int, SearchHit]]], cited: list[str]) -> None:
        budget = self._gateway.budget_left()
        likely = {url: self._likelihood(found[url]) for url in found}
        sure = [url for url in found if url not in cited and self._names_company(found[url][0][1])]
        doubtful = sorted((url for url in found if url not in cited and url not in sure), key=lambda url: -likely[url])
        if self._gateway.time_is_short():       # slow providers: no time for the check, so render them all
            mentioned, sure, doubtful = [], sure + doubtful, []
        else:
            mentioned = self._mentioning(doubtful[:int(budget * PREFILTER_SHARE)])
        for url in mentioned:
            likely[url] += MENTION_BONUS
        ranked = sorted(sure + mentioned, key=lambda url: -likely[url])
        batch = list(dict.fromkeys(cited + ranked))[:self._gateway.budget_left() // RENDERED_EXTRACT_COST]
        texts = self._fan_out([lambda u=url: self._gateway.extract_rendered(u) for url in batch])
        for url, text in zip(batch, texts):
            if text:
                self._evidence.add_page(url, "nimble", text)

    def _mentioning(self, urls: list[str]) -> list[str]:
        """The pages among ``urls`` whose served text names the company."""
        texts = self._fan_out([lambda u=url: self._gateway.extract_plain(u) for url in urls])
        return [url for url, text in zip(urls, texts) if text and names_company(parse_served_text(text).prose, self._domain)]

    def _names_company(self, hit: SearchHit) -> bool:
        """Whether a page's host, URL, title or snippet shows it is about the company."""
        host = normalise_domain(urlparse(hit.url).hostname or "")
        shown = _SEPARATORS.sub(" ", f"{hit.url} {hit.title} {hit.text}").lower()
        return host == self._domain or company_name(self._domain).lower() in shown or self._domain in hit.url.lower()

    def _likelihood(self, appearances: list[tuple[int, SearchHit]]) -> float:
        """How likely a page found by search is to state a fact about the company, judged from what search showed."""
        hit = appearances[0][1]
        host = normalise_domain(urlparse(hit.url).hostname or "")
        score = 3.0 if host == self._domain else 0.0
        if self._names_company(hit):
            score += 2.0
        if any(supported_value(field, sentence, self._domain) is not None
               for sentence in citable_sentences(parse_served_text(hit.text).prose) for field in SLOTS):
            score += 2.0
        return score + sum(1.0 - 0.05 * rank for rank, _ in appearances)

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
