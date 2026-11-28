"""Evidence a build gathers: the pages it read and the candidates their text supports."""
from __future__ import annotations

from dataclasses import dataclass, replace

from .clock import try_parse_timestamp
from .lineage import PageLineage, host_of, missing_original, origin_of, parse_lineage
from .pages import citable_sentences, parse_served_text
from .selection import KINDS, Candidate
from .support import SLOTS, slot_values
from .versions import PageVersion, page_true_from


def page_kind(header: dict[str, str], url: str, domain: str, lineage: PageLineage) -> str:
    """The page's kind. It is ``own`` only when its registrant is the company: a page that states
    ``Kind: own`` for another registrant is an aggregator. Without a listed kind, the company's own host is ``own``."""
    stated = header.get("Kind", "").strip()
    if stated in KINDS and stated != "own":
        return stated
    own = lineage.registrant == domain and (stated == "own" or host_of(url) == domain)
    return "own" if own else "aggregator"


def published_at(header: dict[str, str]) -> str | None:
    """The page's ``Published`` line as an RFC 3339 timestamp, else None."""
    moment = try_parse_timestamp(header.get("Published", "").strip())
    return moment.isoformat() if moment is not None else None


@dataclass(frozen=True)
class _Page:
    url: str
    true_from: str | None
    lineage: PageLineage
    candidates: tuple[tuple[str, Candidate], ...]


class Evidence:
    """The page versions of one company that one build gathered: the pages it read and what they support.

    Origins are settled when the pages are asked for: each page's origin follows its lineage, through
    the originals that ``note_served`` has been told about.
    """

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self._pages: list[_Page] = []
        self._served: dict[str, PageLineage | None] = {}    # URL -> lineage of the page served there, None when no page

    def add_page(self, url: str, provider: str, text: str) -> None:
        """Read the text a provider served for ``url``: every value one of its sentences supports is a candidate."""
        parsed = parse_served_text(text)
        lineage = parse_lineage(parsed.header, url)
        self._served[url] = lineage
        kind = page_kind(parsed.header, url, self.domain, lineage)
        published = published_at(parsed.header)
        true_from = page_true_from(parsed.header, published)
        seen: set[tuple[str, object]] = set()
        found: list[tuple[str, Candidate]] = []
        for sentence in citable_sentences(parsed.prose):
            for slot in SLOTS:
                for value in slot_values(slot, sentence, self.domain):
                    if (slot, value) not in seen:
                        seen.add((slot, value))
                        found.append((slot, Candidate(value, url, sentence, provider, kind, published,
                                                      true_from=true_from)))
        self._pages.append(_Page(url, true_from, lineage, tuple(found)))

    def note_served(self, url: str, text: str | None) -> None:
        """Remember the lineage of the page at ``url``: from a text served for it, or None when none was."""
        if text is None:
            self._served[url] = None
        elif url not in self._served or self._served[url] is None:
            self._served[url] = parse_lineage(parse_served_text(text).header, url)

    def knows(self, url: str) -> bool:
        return url in self._served

    def unresolved(self) -> list[str]:
        """The originals still to be looked up: URLs that the origin of a page with candidates depends on."""
        wanted: dict[str, None] = {}
        for page in self._pages:
            if page.candidates:
                url = missing_original(page.lineage, self._lookup)
                if url is not None:
                    wanted[url] = None
        return list(wanted)

    def pages(self) -> list[PageVersion]:
        """The pages read, each candidate carrying its origin; an original nobody could look up is its URL's host."""
        out = []
        for page in self._pages:
            origin = origin_of(page.lineage, self.domain, lambda url: self._served.get(url))
            out.append(PageVersion(page.url, page.true_from,
                                   tuple((slot, replace(c, origin=origin)) for slot, c in page.candidates)))
        return out

    def _lookup(self, url: str) -> tuple[bool, PageLineage | None]:
        return url in self._served, self._served.get(url)
