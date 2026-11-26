"""Every provider call, through WebRouter, with cost accounting and bounded retries.

Costs follow spec section 9 and stage 2. A call a provider refuses with an error status costs
nothing and may be retried (a 429 after a pause of more than a second, as the provider asks); a
call whose answer never arrives costs its units and is never retried (the provider may have done
the work). An extract answered without a page is charged.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from web_router import ProviderError, ResearchTimeoutError, WebRouter
from web_router.exceptions_typed import ExtractFailedError

from .config import Settings
from .ledger import BudgetExhausted, Ledger
from .support import FIELDS

SEARCH_COST = 1                # every search is a nimble ``lite`` search
RENDERED_EXTRACT_COST = 3      # per URL: Nimble loads the page in a browser
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
        self._pause_lock = threading.Lock()
        self._sleepers = 0
        self._sleeping_since = 0.0
        self._slept = 0.0
        self.successes = 0

    def working_time(self) -> float:
        """Time the build has run, not counting the time it spent waiting to repeat a call after a 429."""
        with self._pause_lock:
            now = time.monotonic()
            waiting = self._slept + (now - self._sleeping_since if self._sleepers else 0.0)
        return now - self._started - waiting

    def _wait_after_rate_limit(self) -> None:
        with self._pause_lock:
            if self._sleepers == 0:
                self._sleeping_since = time.monotonic()
            self._sleepers += 1
        time.sleep(RATE_LIMIT_PAUSE)
        with self._pause_lock:
            self._sleepers -= 1
            if self._sleepers == 0:
                self._slept += time.monotonic() - self._sleeping_since

    def budget_left(self) -> int:
        return self._ledger.remaining()

    def can_research(self) -> bool:
        return self.working_time() < self._settings.research_start_limit and self._ledger.remaining() >= RESEARCH_COST

    def window_open(self) -> bool:
        return not self._stopped() and self.working_time() < self._settings.gather_window

    def _call(self, operation: str, cost: int, call: Callable[[], object]):
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
                if charged:
                    raise CallFailed(str(error)) from error
                kind, status = getattr(error, "kind", None), getattr(error, "status_code", 0) or 0
                if kind == "rate_limit" and rate_limited < RATE_LIMIT_RETRIES:
                    rate_limited += 1
                    self._wait_after_rate_limit()
                elif kind == "upstream" and status >= 500 and server_errors < SERVER_ERROR_RETRIES:
                    server_errors += 1
                    time.sleep(SERVER_ERROR_PAUSE)
                else:
                    raise CallFailed(str(error)) from error
                continue
            self._ledger.settle(cost, True)
            self.successes += 1
            return result

    def search(self, query: str) -> list[SearchHit]:
        response = self._call("search", SEARCH_COST, lambda: self._router.search(
            query, provider=PROVIDER, max_results=10, search_depth="lite", data_apis=False))
        raw_items = (response.raw or {}).get("results") or []
        hits = []
        for index, result in enumerate(response.results):
            raw = raw_items[index] if index < len(raw_items) and isinstance(raw_items[index], dict) else {}
            text = raw.get("content") or raw.get("description") or result.content or result.description or ""
            hits.append(SearchHit(result.url, result.title or "", text))
        return hits

    def extract_rendered(self, url: str) -> str | None:
        """The text a browser shows for ``url`` once it has loaded; None when the provider has no page for it."""
        try:
            response = self._call("extract", RENDERED_EXTRACT_COST, lambda: self._router.extract(
                [url], provider=PROVIDER, data_apis=False, provider_options={"render": True}))
        except CallFailed as failure:
            if isinstance(failure.__cause__, ExtractFailedError):
                return None
            raise
        return response.documents[0].content if response.documents else None

    def research(self, query: str) -> list[str]:
        """Run one research run asking for all six fields: the URLs of the pages its claims cite."""
        timeout = min(self._settings.research_timeout, max(self._settings.hard_limit - self.working_time(), 10.0))
        response = self._call("research", RESEARCH_COST, lambda: self._router.research(
            query, provider=PROVIDER, output_schema=_RESEARCH_SCHEMA, timeout=timeout))
        cited = []
        for citation in response.citations or []:
            field = (citation.field or "").removeprefix("$.")
            if field in FIELDS and citation.url and citation.url not in cited:
                cited.append(citation.url)
        return cited
