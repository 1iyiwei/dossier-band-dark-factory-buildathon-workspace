"""Domain normalisation and validation (spec section 4, Domains)."""
from __future__ import annotations

import re

_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)
_ASCII_UPPER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def normalise_domain(raw: str) -> str:
    """Strip whitespace, lowercase, drop one trailing '.' and one leading 'www.'."""
    domain = raw.strip().translate(_ASCII_UPPER)
    if domain.endswith("."):
        domain = domain[:-1]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def is_valid_domain(domain: str) -> bool:
    """A normalised domain is two or more valid labels, 253 characters at most."""
    if not domain or len(domain) > 253:
        return False
    labels = domain.split(".")
    return len(labels) >= 2 and all(_LABEL.fullmatch(label) for label in labels)


def parse_domain(raw: str) -> str | None:
    """Normalise ``raw``; None when the result is not a valid host name."""
    domain = normalise_domain(raw)
    return domain if is_valid_domain(domain) else None


def company_name(domain: str) -> str:
    """The first label of the domain with each '-' read as a space."""
    return domain.split(".")[0].replace("-", " ")
