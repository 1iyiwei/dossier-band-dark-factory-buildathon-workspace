"""Where a page's material comes from: registrant, copies, republications and the origin they lead to.

A page's header (``Registrant``, ``Canonical``, ``First-Published-By``) says who publishes it and
whether it copies or republishes another. Pages with the same origin are one source.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from .domains import normalise_domain, parse_domain

MAX_CANONICAL_HOPS = 3      # origin follows at most this many ``Canonical`` URLs in a row


@dataclass(frozen=True)
class PageLineage:
    """What a page's header says about its publisher and its sources."""
    registrant: str                  # the domain whose owner publishes the page
    first_published_by: str | None   # the domain that first published the material the page republishes
    canonical: str | None            # the URL of the original when this page is a copy
    lookalike: bool                  # claims ``Kind: own`` for a company it is not registered to


def host_of(url: str) -> str:
    """The host of ``url``, normalised as a domain; empty when it has none."""
    try:
        return normalise_domain(urlparse(url).hostname or "")
    except ValueError:
        return ""


def parse_lineage(header: dict[str, str], url: str) -> PageLineage:
    """The lineage a page's header states; a missing or invalid ``Registrant`` is the page's own host."""
    host = host_of(url)
    registrant = parse_domain(header.get("Registrant", "")) or host
    canonical = header.get("Canonical", "").strip()
    return PageLineage(
        registrant=registrant,
        first_published_by=parse_domain(header.get("First-Published-By", "")),
        canonical=canonical if canonical and canonical != url and host_of(canonical) else None,
        lookalike=header.get("Kind", "").strip() == "own" and registrant != host)


def origin_of(page: PageLineage, company: str, original: Callable[[str], PageLineage | None]) -> str:
    """The origin of ``page``: its first publisher, else its original's origin, else the company or its registrant.

    ``original`` gives the lineage of the page served at a URL, or None where no provider serves one.
    """
    hops = 0
    while True:
        if page.first_published_by:
            return page.first_published_by
        if page.canonical is None:
            return company if page.lookalike else page.registrant
        followed = original(page.canonical) if hops < MAX_CANONICAL_HOPS else None
        if followed is None:
            return host_of(page.canonical)
        page, hops = followed, hops + 1


def missing_original(page: PageLineage, original: Callable[[str], tuple[bool, PageLineage | None]]) -> str | None:
    """The first URL in ``page``'s chain of originals that nobody has looked up yet, or None.

    ``original`` gives (looked up, lineage) for a URL.
    """
    hops = 0
    while page.first_published_by is None and page.canonical is not None and hops < MAX_CANONICAL_HOPS:
        looked_up, followed = original(page.canonical)
        if not looked_up:
            return page.canonical
        if followed is None:
            return None
        page, hops = followed, hops + 1
    return None
