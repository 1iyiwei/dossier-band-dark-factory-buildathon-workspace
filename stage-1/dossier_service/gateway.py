"""Every provider call, through WebRouter, with cost accounting and bounded retries.

Costs follow spec section 9. A call a provider refuses with an error status costs nothing
and may be retried; a call whose answer never arrives costs its units and is never retried
(the provider may have done the work). An extract answered without a page is charged.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from web_router import ProviderError, ResearchTimeoutError, WebRouter
from web_router.exceptions_typed import ExtractFailedError

from .config import Settings
from .ledger import BudgetExhausted, Ledger
from .support import FIELDS

SEARCH_COST = {"lite": 1, "fast": 5, "deep": 15}
EXTRACT_COST = 1
RESEARCH_COST = 25
PROVIDER = "nimble"
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_PAUSE = 1.05        # the provider answers a repeat inside one second with 429 again
SERVER_ERROR_RETRIES = 1
SERVER_ERROR_PAUSE = 0.4
_REFUSAL_KINDS = {"auth", "rate_limit", "bad_request", "upstream"}

_RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "legal_name": {"type": ["string", "null"]},
        "hq_city": {"type": ["string", "null"]},
        "ceo": {"type": ["string", "null"]},
        "founded_year": {"type": ["integer", "null"]},
        "headcount_range": {"type": ["string", "null"]},
        "funding_total": {"type": ["integer", "null"]},
    },
}
assert tuple(_RESEARCH_SCHEMA["properties"]) == FIELDS


class CallFailed(Exception):
    """A provider call ended without an answer the build can use."""


class BuildStopped(Exception):
    """The build was cancelled (reset or import) or has used its time window."""


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    text: str


@dataclass(frozen=True)
class ResearchCitation:
    url: str
    field: str
    claimed: object
    excerpts: list[str]


def make_router() -> WebRouter:
    """The one WebRouter the service uses. It reads NIMBLE_API_KEY and NIMBLE_BASE_URL itself."""
    settings = Settings.from_env()
    return WebRouter(PROVIDER, provider_config={
        PROVIDER: {"timeout": settings.call_timeout, "max_retries": 0}})


def _charged(error: Exception, operation: str) -> bool:
    """Whether a failed call still cost its units."""
    if isinstance(error, ResearchTimeoutError):
        return True
    if operation == "extract" and isinstance(error, ExtractFailedError):
        return True                       # answered, with no page for the URL
    status = getattr(error, "status_code", None)
    kind = getattr(error, "kind", None)
    return not (status is not None and kind in _REFUSAL_KINDS)


class Gateway:
    """The provider calls of one build."""

    def __init__(self, router: WebRouter, settings: Settings, ledger: Ledger,
                 stop_check: Callable[[], bool]) -> None:
        self._router = router
        self._settings = settings
        self._ledger = ledger
        self._stopped = stop_check
        self._started = time.monotonic()
        self.successes = 0

    def elapsed(self) -> float:
        return time.monotonic() - self._started

    def can_research(self) -> bool:
        return self.elapsed() < self._settings.research_start_limit and self._ledger.remaining() >= RESEARCH_COST

    def window_open(self) -> bool:
        return not self._stopped() and self.elapsed() < self._settings.gather_window

    def _call(self, operation: str, cost: int, call: Callable[[], object], patience: int):
        rate_limited = server_errors = 0
        while True:
            if not self.window_open():
                raise BuildStopped()
            self._ledger.reserve(cost)
            try:
                result = call()
            except Exception as error:   # noqa: BLE001 - every provider failure is classified below
                charged = _charged(error, operation)
                self._ledger.settle(cost, charged)
                if charged or patience == 0:
                    raise CallFailed(str(error)) from error
                kind, status = getattr(error, "kind", None), getattr(error, "status_code", 0) or 0
                if kind == "rate_limit" and rate_limited < patience:
                    rate_limited += 1
                    time.sleep(RATE_LIMIT_PAUSE)
                elif kind == "upstream" and status >= 500 and server_errors < SERVER_ERROR_RETRIES:
                    server_errors += 1
                    time.sleep(SERVER_ERROR_PAUSE)
                else:
                    raise CallFailed(str(error)) from error
                continue
            self._ledger.settle(cost, True)
            self.successes += 1
            return result

    def search(self, query: str, depth: str, patience: int = RATE_LIMIT_RETRIES) -> list[SearchHit]:
        response = self._call("search", SEARCH_COST[depth], lambda: self._router.search(
            query, provider=PROVIDER, max_results=10, search_depth=depth, data_apis=False), patience)
        raw_items = (response.raw or {}).get("results") or []
        hits = []
        for index, result in enumerate(response.results):
            raw = raw_items[index] if index < len(raw_items) and isinstance(raw_items[index], dict) else {}
            text = raw.get("content") or raw.get("description") or result.content or result.description or ""
            hits.append(SearchHit(result.url, result.title or "", text))
        return hits

    def extract(self, url: str) -> str | None:
        """The whole served text of ``url``; None when the provider has no page for it."""
        try:
            response = self._call("extract", EXTRACT_COST, lambda: self._router.extract(
                [url], provider=PROVIDER, data_apis=False), RATE_LIMIT_RETRIES)
        except CallFailed as failure:
            if isinstance(failure.__cause__, ExtractFailedError):
                return None
            raise
        return response.documents[0].content if response.documents else None

    def research(self, query: str) -> tuple[dict, list[ResearchCitation]]:
        """Run one research run asking for all six fields: its claims and their citations."""
        timeout = min(self._settings.research_timeout, max(self._settings.hard_limit - self.elapsed(), 10.0))
        response = self._call("research", RESEARCH_COST, lambda: self._router.research(
            query, provider=PROVIDER, output_schema=_RESEARCH_SCHEMA, timeout=timeout), RATE_LIMIT_RETRIES)
        claims = response.structured if isinstance(response.structured, dict) else {}
        citations = []
        for citation in response.citations or []:
            field = (citation.field or "").removeprefix("$.")
            if field not in FIELDS:
                continue
            excerpts = list((citation.extra or {}).get("excerpts") or [])
            if citation.snippet and citation.snippet not in excerpts:
                excerpts.insert(0, citation.snippet)
            citations.append(ResearchCitation(citation.url, field, claims.get(field),
                                              [e for e in excerpts if isinstance(e, str)]))
        return claims, citations
