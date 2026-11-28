"""Evidence a build gathers: the pages it read and the candidates their text supports."""
from __future__ import annotations

from urllib.parse import urlparse

from .clock import try_parse_timestamp
from .domains import normalise_domain
from .pages import citable_sentences, parse_served_text
from .selection import KINDS, Candidate
from .support import SLOTS, supported_value
from .versions import PageVersion, page_true_from


def page_kind(header: dict[str, str], url: str, domain: str) -> str:
    """The page's ``Kind`` line when it is a listed kind, else own for the company's host, else aggregator."""
    kind = header.get("Kind", "").strip()
    if kind in KINDS:
        return kind
    host = normalise_domain(urlparse(url).hostname or "")
    return "own" if host == domain else "aggregator"


def published_at(header: dict[str, str]) -> str | None:
    """The page's ``Published`` line as an RFC 3339 timestamp, else None."""
    moment = try_parse_timestamp(header.get("Published", "").strip())
    return moment.isoformat() if moment is not None else None


class Evidence:
    """The page versions of one company that one build gathered: the pages it read and what they support."""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self._pages: list[PageVersion] = []

    def add_page(self, url: str, provider: str, text: str) -> None:
        """Read the text a provider served for ``url``: every value one of its sentences supports is a candidate."""
        parsed = parse_served_text(text)
        kind = page_kind(parsed.header, url, self.domain)
        published = published_at(parsed.header)
        true_from = page_true_from(parsed.header, published)
        seen: set[tuple[str, object]] = set()
        found: list[tuple[str, Candidate]] = []
        for sentence in citable_sentences(parsed.prose):
            for slot in SLOTS:
                value = supported_value(slot, sentence, self.domain)
                if value is None or (slot, value) in seen:
                    continue
                seen.add((slot, value))
                found.append((slot, Candidate(value, url, sentence, provider, kind, published, true_from=true_from)))
        self._pages.append(PageVersion(url, true_from, tuple(found)))

    def pages(self) -> list[PageVersion]:
        return list(self._pages)
