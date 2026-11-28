"""Stage-4 lineage model, written from stage-4.md alone: registrant, lookalike, origin of a page (the four rules,
the three-Canonical limit), and the originals a build needs. Pure functions over the corpus (mock-web format)."""
from __future__ import annotations

import s2model as m

MAX_FOLLOW = 3          # "rule 2 follows at most three Canonical URLs in a row"


def header(entry, key):
    return ((entry or {}).get("lineage") or {}).get(key)


def registrant(entry, url):
    """The page's registrant: its `Registrant` line (normalised, valid) else the host of its own URL."""
    return m.registrant_of(entry, url)


def first_published_by(entry):
    """`First-Published-By` domain, normalised as in §4; an invalid value is no line (RULINGS 77)."""
    return m.valid_domain(header(entry, "first_published_by"))


def canonical(entry, url):
    """`Canonical` URL when it is not the page's own URL, else None."""
    c = header(entry, "canonical")
    if not isinstance(c, str) or not c.strip() or c.strip() == url:
        return None
    return c.strip()


def is_lookalike(entry, url):
    """A page that states `Kind: own` and whose registrant is not the host of its own URL."""
    return (entry or {}).get("kind") == "own" and registrant(entry, url) != m.host_of(url)


def make_lookup(corpus, epoch):
    """url -> corpus page entry served in `epoch` (any company: the mock serves every page of the epoch)."""
    idx = {}
    for comp in corpus.values():
        for p in comp["pages"]:
            if epoch in p["epochs"]:
                idx[p["url"]] = p
    return idx.get


def origin(entry, url, domain, lookup, hops=0, needed=None):
    """stage-4.md Origins: 1 First-Published-By; 2 the origin of the page at the Canonical URL (at most three
    Canonical URLs followed in a row; a fourth, or an unserved URL, gives the host of that URL); 3 the company's
    domain for a lookalike; 4 the registrant."""
    fpb = first_published_by(entry)
    if fpb:
        return fpb
    canon = canonical(entry, url)
    if canon:
        if needed is not None and hops < MAX_FOLLOW:
            needed.append(canon)
        if hops >= MAX_FOLLOW:
            return m.host_of(canon)
        orig = lookup(canon)
        if orig is None:
            return m.host_of(canon)
        return origin(orig, canon, domain, lookup, hops + 1, needed)
    if is_lookalike(entry, url):
        return domain
    return registrant(entry, url)


def origins_of_epoch(domain, epoch, corpus, pages):
    """{url: origin} for the given pages (corpus entries of the epoch's evidence), and the originals needed."""
    lookup = make_lookup(corpus, epoch)
    needed = []
    out = {url: origin(p, url, domain, lookup, 0, needed) for url, p in pages.items()}
    return out, needed
