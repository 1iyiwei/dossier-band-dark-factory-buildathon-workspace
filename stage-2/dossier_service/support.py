"""Appendix A: when an excerpt supports a value for a field.

This module is the whole definition of "supports" used by the service. Every citation the
service asserts is checked here first (``supported_value``); nothing else decides support.
"""
from __future__ import annotations

import re
from decimal import Decimal

from .domains import company_name

FIELDS = ("legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total")

PHRASES = {
    "legal_name": ("legal name", "registered name", "registered as", "registered company",
                   "legal entity", "name of record"),
    "hq_city": ("headquartered in", "headquarters in", "head office in", "based in",
                "registered office in", "registered seat in"),
    "ceo": ("chief executive officer", "chief executive", "CEO"),
    "founded_year": ("founded", "founding", "established", "incorporated"),
    "headcount_range": ("employs", "employees", "staff", "people", "headcount", "workforce"),
    "funding_total": ("raised", "funding", "invested", "investment"),
}

NEGATING = ("in talks to", "plans to", "planning to", "wants to", "expects to", "hopes to",
            "aims to", "seeking", "could", "would", "might", "reportedly", "rumoured", "former",
            "formerly", "will become", "not")

LEGAL_SUFFIXES = (
    "Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC", "GmbH",
    "AG", "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.", "S.A.", "S.A.S.",
    "S.L.", "S.r.l.", "S.p.A.", "s.r.o.", "a.s.", "K.K.",
)
_DOTTED_SUFFIXES = tuple(s for s in LEGAL_SUFFIXES if s.endswith("."))

HEADCOUNT_RANGES = (
    (1, 10, "1-10"), (11, 50, "11-50"), (51, 200, "51-200"), (201, 500, "201-500"),
    (501, 1000, "501-1000"), (1001, 5000, "1001-5000"), (5001, 10000, "5001-10000"),
)
OPEN_RANGE = "10001+"

_CLOSERS = '"”’)'
_NOT_ALNUM_BEFORE = r"(?<![^\W_])"
_NOT_ALNUM_AFTER = r"(?![^\W_])"
_WS = re.compile(r"\s+")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")


# ---------------------------------------------------------------- A.1 sentences

def _ends_legal_suffix(line: str, dot_index: int) -> bool:
    head = line[: dot_index + 1]
    for suffix in _DOTTED_SUFFIXES:
        if head.endswith(suffix):
            before = len(head) - len(suffix) - 1
            if before < 0 or not line[before].isalnum():
                return True
    return False


def _split_line(line: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    size = len(line)
    for i, ch in enumerate(line):
        if ch not in ".!?":
            continue
        end = i + 1
        while end < size and line[end] in _CLOSERS:
            end += 1
        if end < size and not line[end].isspace():
            continue
        if ch == "." and _ends_legal_suffix(line, i):
            continue
        sentences.append(line[start:end])
        start = end
    sentences.append(line[start:])
    return [s.strip() for s in sentences if s.strip()]


def split_sentences(prose: str) -> list[str]:
    """Split prose into sentences: lines first, then A.1's terminator rule."""
    sentences: list[str] = []
    for line in _LINE_BREAK.split(prose):
        sentences.extend(_split_line(line))
    return sentences


def collapse_whitespace(text: str) -> str:
    return _WS.sub(" ", text).strip()


def is_single_sentence(excerpt: str) -> bool:
    return len(split_sentences(collapse_whitespace(excerpt))) == 1


# ---------------------------------------------------------------- phrase matching

def _phrase_regex(phrase: str) -> re.Pattern[str]:
    return re.compile(_NOT_ALNUM_BEFORE + re.escape(phrase) + _NOT_ALNUM_AFTER, re.IGNORECASE)


_PHRASE_CACHE: dict[str, re.Pattern[str]] = {}


def phrase_matches(text: str, phrase: str) -> list[re.Match[str]]:
    pattern = _PHRASE_CACHE.get(phrase)
    if pattern is None:
        pattern = _PHRASE_CACHE[phrase] = _phrase_regex(phrase)
    return list(pattern.finditer(text))


def has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase_matches(text, p) for p in phrases)


# ---------------------------------------------------------------- A.4 words and numbers

def _words(text: str) -> list[tuple[int, int, str]]:
    """Maximal runs of letters and digits."""
    return [(m.start(), m.end(), m.group()) for m in re.finditer(r"[^\W_]+", text)]


def is_capitalised(word: str) -> bool:
    return len(word) >= 2 and word[0].isupper() and all(c.islower() for c in word[1:])


def is_uppercase_word(word: str) -> bool:
    return len(word) >= 2 and all(c.isalpha() and c.isupper() for c in word)


_CHAIN = re.compile(r"\d+(?:[.,]\d+)*")
_NUMBER_SHAPE = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
_NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"


class _Number:
    __slots__ = ("start", "end", "text")

    def __init__(self, start: int, end: int, text: str) -> None:
        self.start, self.end, self.text = start, end, text

    @property
    def has_decimal(self) -> bool:
        return "." in self.text

    @property
    def value(self) -> Decimal:
        return Decimal(self.text.replace(",", ""))


def _numbers(text: str) -> list[_Number]:
    """Numbers in the sense of A.4: digit chains of a valid shape not next to a letter."""
    found = []
    for m in _CHAIN.finditer(text):
        if not _NUMBER_SHAPE.fullmatch(m.group()):
            continue
        if m.start() > 0 and text[m.start() - 1].isalpha():
            continue
        if m.end() < len(text) and text[m.end()].isalpha():
            continue
        found.append(_Number(m.start(), m.end(), m.group()))
    return found


def _joined_digit(text: str, index: int, step: int) -> bool:
    """True when text[index] is a '.' or ',' with a digit beyond it in direction ``step``."""
    beyond = index + step
    return 0 <= index < len(text) and text[index] in ".," and 0 <= beyond < len(text) and text[beyond].isdigit()


_SCALES = {"k": 1_000, "m": 1_000_000, "mn": 1_000_000, "bn": 1_000_000_000,
           "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
_AMOUNT_SYMBOL = re.compile(
    _NOT_ALNUM_BEFORE + r"(?:\$|US\$|USD) ?(?P<num>" + _NUM + r")"
    r"(?:(?P<scale>k|mn|bn|m)|(?: (?P<word>thousand|million|billion)))?" + _NOT_ALNUM_AFTER,
    re.IGNORECASE)
_AMOUNT_WORD = re.compile(
    _NOT_ALNUM_BEFORE + r"(?P<num>" + _NUM + r")(?: (?P<word>thousand|million|billion))?"
    r" (?:US )?dollars" + _NOT_ALNUM_AFTER, re.IGNORECASE)


def _amounts(text: str) -> list[tuple[int, int, int | None]]:
    """Amounts as (start, end, whole-dollar value or None when not a whole number)."""
    found = []
    for pattern in (_AMOUNT_SYMBOL, _AMOUNT_WORD):
        for m in pattern.finditer(text):
            num_start, num_end = m.span("num")
            if _joined_digit(text, num_end, 1) or _joined_digit(text, num_start - 1, -1):
                continue
            scale = (m.groupdict().get("scale") or m.groupdict().get("word") or "").lower()
            total = Decimal(m.group("num").replace(",", "")) * _SCALES.get(scale, 1)
            found.append((m.start(), m.end(), int(total) if total == total.to_integral_value() else None))
    return found


def _outside(spans: list[tuple[int, int, int | None]], number: _Number) -> bool:
    return not any(start <= number.start < end for start, end, _ in spans)


def headcount_range(count: int) -> str:
    for low, high, label in HEADCOUNT_RANGES:
        if low <= count <= high:
            return label
    return OPEN_RANGE


# ---------------------------------------------------------------- per-field value finders

def _legal_names(text: str, domain: str) -> list[str]:
    values = []
    for anchor in (company_name(domain), domain):
        for m in phrase_matches(text, anchor):
            value = _legal_name_from(text, m.end())
            if value is not None:
                values.append(text[m.start():value])
    return values


def _legal_name_from(text: str, position: int) -> int | None:
    """End index of the shortest 'words, optional comma, suffix' continuation, or None."""
    while True:
        ends = []
        for suffix in LEGAL_SUFFIXES:
            for lead in (" ", ", "):
                if text.startswith(lead + suffix, position):
                    end = position + len(lead) + len(suffix)
                    if end == len(text) or not text[end].isalnum():
                        ends.append(end)
        if ends:
            return min(ends)
        word = re.match(r" ([^\W_]+)", text[position:])
        if word is None or not (is_capitalised(word.group(1)) or is_uppercase_word(word.group(1))):
            return None
        position += word.end()


def _capitalised_run_after(text: str, position: int, joiners: str) -> str | None:
    words = _words(text)
    starts = {start: idx for idx, (start, _, _) in enumerate(words)}
    if position not in starts:
        return None
    idx = starts[position]
    if not is_capitalised(words[idx][2]):
        return None
    last = idx
    while last + 1 < len(words):
        gap = text[words[last][1]:words[last + 1][0]]
        if gap in tuple(joiners) and is_capitalised(words[last + 1][2]):
            last += 1
        else:
            break
    return text[words[idx][0]:words[last][1]]


def _cities(text: str) -> list[str]:
    values = []
    for phrase in PHRASES["hq_city"]:
        for m in phrase_matches(text, phrase):
            if text.startswith(" ", m.end()):
                run = _capitalised_run_after(text, m.end() + 1, " -")
                if run is not None:
                    values.append(run)
    return values


def _people(text: str, domain: str) -> list[str]:
    scrubbed = text
    removable = [company_name(domain), *sorted(PHRASES["ceo"], key=len, reverse=True)]
    for phrase in removable:
        scrubbed = _phrase_regex(phrase).sub("\x00", scrubbed)
    words = _words(scrubbed)
    values, run = [], []

    def flush() -> None:
        if 2 <= len(run) <= 3:
            values.append(scrubbed[run[0][0]:run[-1][1]])
        run.clear()

    for start, end, word in words:
        joined = run and scrubbed[run[-1][1]:start] == " "
        if not is_capitalised(word):
            flush()
        elif run and not joined:
            flush()
            run.append((start, end))
        else:
            run.append((start, end))
    flush()
    return values


def _years(text: str) -> list[int]:
    amounts = _amounts(text)
    return [int(n.text) for n in _numbers(text)
            if re.fullmatch(r"\d{4}", n.text) and 1800 <= int(n.text) <= 2099 and _outside(amounts, n)]


def _headcounts(text: str) -> list[str]:
    amounts = _amounts(text)
    return [headcount_range(int(n.value)) for n in _numbers(text)
            if not n.has_decimal and n.value >= 1 and _outside(amounts, n)]


def _fundings(text: str) -> list[int]:
    return [value for _, _, value in _amounts(text) if value is not None]


def candidate_values(field: str, text: str, domain: str) -> list:
    """Every value in ``field``'s format (A.4) that ``text`` contains, normalised (A.5)."""
    if field == "legal_name":
        return _legal_names(text, domain)
    if field == "hq_city":
        return _cities(text)
    if field == "ceo":
        return _people(text, domain)
    if field == "founded_year":
        return _years(text)
    if field == "headcount_range":
        return _headcounts(text)
    if field == "funding_total":
        return _fundings(text)
    raise ValueError(field)


# ---------------------------------------------------------------- A.2 the rule

def names_company(text: str, domain: str) -> bool:
    return bool(phrase_matches(text, domain) or phrase_matches(text, company_name(domain)))


def supported_value(field: str, excerpt: str, domain: str):
    """The value ``excerpt`` supports for ``field`` of the company at ``domain``, else None."""
    if not 1 <= len(excerpt) <= 500 or excerpt != collapse_whitespace(excerpt):
        return None
    if not is_single_sentence(excerpt):
        return None
    if not names_company(excerpt, domain):
        return None
    if not has_any_phrase(excerpt, PHRASES[field]):
        return None
    if has_any_phrase(excerpt, NEGATING):
        return None
    values = candidate_values(field, excerpt, domain)
    if not values or any(v != values[0] for v in values):
        return None
    return values[0]
