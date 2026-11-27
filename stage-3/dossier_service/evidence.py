"""Evidence a build gathers: the pages it read and the candidates their text supports."""
from __future__ import annotations

from urllib.parse import urlparse

from .clock import try_parse_timestamp
from .domains import normalise_domain
from .pages import citable_sentences, parse_served_text
from .selection import KINDS, Candidate
from .support import FIELDS, supported_value


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
    """The candidates of one company, gathered from the browser text of the pages one build read."""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self._candidates: dict[str, list[Candidate]] = {f: [] for f in FIELDS}
        self._seen: set[tuple[str, str, object]] = set()

    def add_page(self, url: str, provider: str, text: str) -> None:
        """Read the text a provider served for ``url``: every value one of its sentences supports is a candidate."""
        parsed = parse_served_text(text)
        kind = page_kind(parsed.header, url, self.domain)
        published = published_at(parsed.header)
        for sentence in citable_sentences(parsed.prose):
            for field in FIELDS:
                value = supported_value(field, sentence, self.domain)
                if value is None or (field, url, value) in self._seen:
                    continue
                self._seen.add((field, url, value))
                self._candidates[field].append(Candidate(value, url, sentence, provider, kind, published))

    def candidates(self) -> dict[str, list[Candidate]]:
        return {field: list(found) for field, found in self._candidates.items()}
