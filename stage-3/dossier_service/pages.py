"""Page text: header lines, prose and the sentences a citation can be taken from."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .support import collapse_whitespace, split_sentences

_HEADER_LINE = re.compile(r"^([A-Z][a-z]+(?:-[A-Z][a-z]+)*): (.*)$")
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


def citable_sentences(prose: str) -> list[str]:
    """Single sentences of ``prose``, whitespace collapsed, at most 500 characters."""
    out = []
    for sentence in split_sentences(prose):
        collapsed = collapse_whitespace(sentence)
        if 1 <= len(collapsed) <= MAX_EXCERPT:
            out.append(collapsed)
    return out
