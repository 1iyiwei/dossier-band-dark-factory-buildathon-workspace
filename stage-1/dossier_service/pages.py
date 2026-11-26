"""Served page text: header lines, prose and the sentences a citation can be taken from."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .support import collapse_whitespace, split_sentences

_HEADER_LINE = re.compile(r"^([A-Z][a-z]+(?:-[A-Z][a-z]+)*): (.*)$")
_TERMINATED = re.compile(r"[.!?][\"”’)]*\s*$")
MAX_EXCERPT = 500


@dataclass(frozen=True)
class ParsedText:
    header: dict[str, str]
    prose: str


def parse_served_text(text: str) -> ParsedText:
    """Split a served text into its header (possibly empty) and its prose."""
    lines = text.split("\n")
    if not lines or not _HEADER_LINE.match(lines[0].rstrip("\r")):
        return ParsedText({}, text)
    header: dict[str, str] = {}
    for index, line in enumerate(lines):
        stripped = line.rstrip("\r")
        if not stripped.strip():
            return ParsedText(header, "\n".join(lines[index + 1:]))
        match = _HEADER_LINE.match(stripped)
        if match:
            header.setdefault(match.group(1), match.group(2).strip())
    return ParsedText(header, "")


def citable_sentences(text: str, cut_short: bool) -> list[str]:
    """Single sentences of the prose of ``text``, whitespace collapsed, at most 500 characters.

    When the served text may have been cut short, an unterminated last sentence is
    dropped: it could be a fragment that says something else.
    """
    prose = parse_served_text(text).prose
    sentences = split_sentences(prose)
    if sentences and cut_short and not _TERMINATED.search(prose):
        sentences = sentences[:-1]
    out = []
    for sentence in sentences:
        collapsed = collapse_whitespace(sentence)
        if 1 <= len(collapsed) <= MAX_EXCERPT:
            out.append(collapsed)
    return out


@dataclass
class Page:
    """Everything one build has been served for one URL."""
    url: str
    title: str = ""
    header: dict[str, str] = field(default_factory=dict)
    full: bool = False          # a text known to be complete has been served

    @property
    def host(self) -> str:
        return (urlparse(self.url).hostname or "").lower()

    @property
    def kind(self) -> str:
        return self.header.get("Kind", "").lower()

    def add(self, text: str, full: bool, title: str = "") -> None:
        """Record a served text; ``full`` says it is the whole page text."""
        if title and not self.title:
            self.title = title
        for name, value in parse_served_text(text).header.items():
            self.header.setdefault(name, value)
        self.full = self.full or full

    def origin(self) -> str:
        """Who first published what the page says; copies share an origin."""
        for name in ("First-Published-By", "Registrant"):
            if self.header.get(name):
                return self.header[name].lower()
        return self.host
