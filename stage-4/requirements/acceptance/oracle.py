"""Independent reference of stage-1 Appendix A ("when an excerpt supports a value").

Written from the specification text only. `supported_values(excerpt, field, domain)` returns
the set of normalised values the excerpt supports for the field (empty: supports nothing,
more than one element: ambiguous so it supports nothing; a citation needs exactly one).
"""
from __future__ import annotations

import re
from decimal import Decimal

FIELDS = ("legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total")
RANGES = [("1-10", 1, 10), ("11-50", 11, 50), ("51-200", 51, 200), ("201-500", 201, 500),
          ("501-1000", 501, 1000), ("1001-5000", 1001, 5000), ("5001-10000", 5001, 10000),
          ("10001+", 10001, 10**18)]
SUFFIXES = ["Inc.", "Corp.", "LLC", "LLP", "L.P.", "Ltd", "Limited", "Pty Ltd", "plc", "PLC",
            "GmbH", "AG", "KG", "SE", "AS", "A/S", "ASA", "AB", "Oy", "Oyj", "B.V.", "N.V.",
            "S.A.", "S.A.S.", "S.L.", "S.r.l.", "S.p.A.", "s.r.o.", "a.s.", "K.K."]
PHRASES = {
    "legal_name": ["legal name", "registered name", "registered as", "registered company",
                   "legal entity", "name of record"],
    "hq_city": ["headquartered in", "headquarters in", "head office in", "based in",
                "registered office in", "registered seat in"],
    "ceo": ["chief executive officer", "chief executive", "CEO"],
    "founded_year": ["founded", "founding", "established", "incorporated"],
    "headcount_range": ["employs", "employees", "staff", "people", "headcount", "workforce"],
    "funding_total": ["raised", "funding", "invested", "investment"],
    # stage 3 (stage-3.md Executives): each title is a field with the format and normalisation of ceo
    "cfo": ["chief financial officer", "CFO"],
    "coo": ["chief operating officer", "COO"],
    "cto": ["chief technology officer", "CTO"],
    # stage 4 (stage-4.md Investors)
    "investors": ["investor", "investors", "led by", "backed by", "participated"],
}
INVESTOR_LAST = ("Ventures", "Capital", "Partners", "Fund", "Investments", "Holdings", "Equity")
TITLES = ("cfo", "coo", "cto")
NEGATING = ["in talks to", "plans to", "planning to", "wants to", "expects to", "hopes to",
            "aims to", "seeking", "could", "would", "might", "reportedly", "rumoured", "former",
            "formerly", "will become", "not"]


def collapse(text: str) -> str:
    return " ".join(text.split())


def alnum(ch: str) -> bool:
    return ch.isalpha() or ch.isdigit()


def find_words(text: str, phrase: str):
    """Yield (start, end) of whole-word, case-insensitive matches of phrase in text."""
    low, p = text.lower(), phrase.lower()
    i = low.find(p)
    while i != -1:
        j = i + len(p)
        if (i == 0 or not alnum(text[i - 1])) and (j == len(text) or not alnum(text[j])):
            yield i, j
        i = low.find(p, i + 1)


def has_phrase(text: str, phrase: str) -> bool:
    return next(find_words(text, phrase), None) is not None


# ---- A.1 sentences
def sentences(text: str) -> list[str]:
    out = []
    for line in re.split(r"\r\n|\r|\n", text):
        start, i, n = 0, 0, len(line)
        while i < n:
            ch = line[i]
            if ch in ".!?":
                j = i + 1
                while j < n and line[j] in "\"”’)":
                    j += 1
                if j < n and line[j].isspace():
                    legal = False
                    if ch == ".":
                        for suf in SUFFIXES:
                            if suf.endswith(".") and line[: i + 1].endswith(suf):
                                b = i + 1 - len(suf)
                                if b == 0 or not alnum(line[b - 1]):
                                    legal = True
                                    break
                    if not legal:
                        out.append(line[start:j].strip())
                        start = j
                i = j
                continue
            i += 1
        out.append(line[start:].strip())
    return [s for s in out if s]


def is_single_sentence(excerpt: str) -> bool:
    return len(sentences(collapse(excerpt))) == 1


# ---- A.4 words and numbers
def is_cap_word(w: str) -> bool:
    return len(w) >= 2 and w[0].isupper() and all(c.islower() for c in w[1:]) and w.isalpha()


def is_upper_word(w: str) -> bool:
    return len(w) >= 2 and w.isalpha() and all(c.isupper() for c in w)


def word_at(text: str, i: int):
    """The maximal letter/digit run starting at i (None if i is inside a run)."""
    if i >= len(text) or not alnum(text[i]) or (i > 0 and alnum(text[i - 1])):
        return None
    j = i
    while j < len(text) and alnum(text[j]):
        j += 1
    return text[i:j]


NUM_CAND = re.compile(r"\d[\d,.]*")
NUM_OK = re.compile(r"^(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


def numbers(text: str):
    """Yield (start, end, string) of every number as defined in A.4."""
    for m in NUM_CAND.finditer(text):
        s, e = m.start(), m.end()
        while e > s and text[e - 1] in ",.":
            e -= 1
        tok = text[s:e]
        if not NUM_OK.match(tok):
            continue
        if s > 0 and alnum(text[s - 1]):
            continue
        if e < len(text) and alnum(text[e]):
            continue
        yield s, e, tok


def num_value(tok: str) -> Decimal:
    return Decimal(tok.replace(",", ""))


SCALE = {"k": 10**3, "thousand": 10**3, "m": 10**6, "mn": 10**6, "million": 10**6,
         "bn": 10**9, "billion": 10**9}


def amounts(text: str):
    """Yield (start, end, Decimal dollars) for each amount (A.4)."""
    low = text.lower()
    found = []
    # form 1: currency marker, optional space, number, optional scale
    for m in re.finditer(r"us\$|usd|\$", low):
        s = m.start()
        if s > 0 and alnum(text[s - 1]):
            continue
        p = m.end()
        if p < len(text) and text[p] == " ":
            p += 1
        mm = NUM_CAND.match(text, p)
        if not mm:
            continue
        ns, ne = mm.start(), mm.end()
        while ne > ns and text[ne - 1] in ",.":
            ne -= 1
        tok = text[ns:ne]
        if not NUM_OK.match(tok):
            continue
        end, scale = ne, 1
        mn = re.match(r"(mn|bn|k|m)(?![A-Za-z0-9])", low[ne:])
        if mn:
            scale, end = SCALE[mn.group(1)], ne + mn.end()
        else:
            mw = re.match(r" (thousand|million|billion)(?![A-Za-z0-9])", low[ne:])
            if mw:
                scale, end = SCALE[mw.group(1)], ne + mw.end()
        if end < len(text) and alnum(text[end]):
            # "$12Mx": scale rejected; try without scale only if next char is not alnum
            continue
        found.append((s, end, num_value(tok) * scale))
    # form 2: number [scale word] dollars
    for ns, ne, tok in numbers(text):
        if ns > 0 and alnum(text[ns - 1]):
            continue
        end, scale = ne, 1
        mw = re.match(r" (thousand|million|billion)", low[ne:])
        if mw:
            scale, end = SCALE[mw.group(1)], ne + mw.end()
        md = re.match(r" (us dollars|dollars)(?![A-Za-z0-9])", low[end:])
        if not md:
            continue
        found.append((ns, end + md.end(), num_value(tok) * scale))
    return found


def in_amount(s: int, e: int, amts) -> bool:
    return any(s >= a and e <= b for a, b, _ in amts)


# ---- values per field (A.4) -> normalised (A.5)
def name_of(domain: str) -> str:
    return domain.split(".")[0].replace("-", " ")


def range_of(n: Decimal):
    for label, lo, hi in RANGES:
        if lo <= n <= hi:
            return label
    return None


def legal_name_values(text: str, domain: str) -> list[str]:
    vals = []
    starts = sorted({s for p in (name_of(domain), domain) for s, _ in find_words(text, p)})
    for s in starts:
        ends = [e for p in (name_of(domain), domain) for s2, e in find_words(text, p) if s2 == s]
        best = None
        for e in ends:
            pos = e
            while True:
                for pre in (", ", " "):
                    if text.startswith(pre, pos):
                        for suf in SUFFIXES:
                            q = pos + len(pre)
                            if text.startswith(suf, q) and not (q + len(suf) < len(text)
                                                               and alnum(text[q + len(suf)])):
                                cand = q + len(suf)
                                if best is None or cand < best:
                                    best = cand
                if best is not None:
                    break
                if text.startswith(" ", pos):
                    w = word_at(text, pos + 1)
                    if w and (is_cap_word(w) or is_upper_word(w)):
                        pos = pos + 1 + len(w)
                        continue
                break
        if best is not None:
            vals.append(text[s:best])
    return vals


def hq_values(text: str) -> list[str]:
    vals = []
    for ph in PHRASES["hq_city"]:
        for _, e in find_words(text, ph):
            if not text.startswith(" ", e):
                continue
            i, words = e + 1, []
            while True:
                w = word_at(text, i)
                if not w or not is_cap_word(w):
                    break
                words.append(w)
                i += len(w)
                if i < len(text) and text[i] in " -" and word_at(text, i + 1) and \
                        is_cap_word(word_at(text, i + 1)):
                    words.append(text[i])
                    i += 1
                    continue
                break
            if words:
                vals.append("".join(words))
    return vals


def ceo_values(text: str, domain: str, title: str = "ceo") -> list[str]:
    chars = list(text)
    for p in [name_of(domain)] + PHRASES[title]:
        for s, e in find_words(text, p):
            for k in range(s, e):
                chars[k] = "\x00"
    t = "".join(chars)
    vals = []
    for seg in t.split("\x00"):
        run = []
        pos = 0
        n = len(seg)
        while pos <= n:
            w = word_at(seg, pos) if pos < n else None
            if w is not None and is_cap_word(w):
                run.append(w)
                pos += len(w)
                if seg.startswith(" ", pos) and word_at(seg, pos + 1) and \
                        is_cap_word(word_at(seg, pos + 1)):
                    pos += 1
                    continue
            if run:
                if 2 <= len(run) <= 3:
                    vals.append(" ".join(run))
                run = []
            if w is not None and not is_cap_word(w):
                pos += len(w)
            else:
                pos += 1
    return vals


def founded_values(text: str) -> list[int]:
    amts = amounts(text)
    return [int(t) for s, e, t in numbers(text)
            if re.fullmatch(r"\d{4}", t) and 1800 <= int(t) <= 2099 and not in_amount(s, e, amts)]


def headcount_values(text: str) -> list[str]:
    amts = amounts(text)
    out = []
    for s, e, t in numbers(text):
        if "." in t or in_amount(s, e, amts):
            continue
        v = num_value(t)
        if v >= 1:
            out.append(range_of(v))
    return out


def funding_values(text: str):
    """(list of normalised ints, count of format values). Non-whole amounts are not values."""
    out = []
    for _, _, v in amounts(text):
        if v == v.to_integral_value():
            out.append(int(v))
    return out


def values_of(text: str, field: str, domain: str) -> list:
    if field == "legal_name":
        return legal_name_values(text, domain)
    if field == "hq_city":
        return hq_values(text)
    if field in ("ceo",) + TITLES:
        return ceo_values(text, domain, field)
    if field == "founded_year":
        return founded_values(text)
    if field == "headcount_range":
        return headcount_values(text)
    return funding_values(text)


def names_company(text: str, domain: str) -> bool:
    return has_phrase(text, domain) or has_phrase(text, name_of(domain))


def supported_values(excerpt: str, field: str, domain: str) -> set:
    """Set of values V such that the excerpt supports V for field (A.2). Empty or >1 element
    sets mean the excerpt supports nothing (the latter: no single V satisfies rule 5)."""
    if field == "investors":
        return investor_names(excerpt, domain)
    t = collapse(excerpt)
    if not (1 <= len(t) <= 500) or not is_single_sentence(t) or not names_company(t, domain):
        return set()
    if not any(has_phrase(t, p) for p in PHRASES[field]):
        return set()
    if any(has_phrase(t, n) for n in NEGATING):
        return set()
    vals = values_of(t, field, domain)
    return set(vals) if len(set(vals)) == 1 else set()


def supports(excerpt: str, field: str, value, domain: str) -> bool:
    if field == "investors":      # an excerpt supports each investor name it contains
        return value in investor_names(excerpt, domain)
    return supported_values(excerpt, field, domain) == {value}


def spans(sentence: str):
    """Candidate excerpts inside a sentence: word-aligned spans (with and without trailing
    punctuation). A superset-free approximation used to decide what *can* be cited."""
    toks = [(m.start(), m.end()) for m in re.finditer(r"\S+", sentence)]
    for a in range(len(toks)):
        for b in range(a, len(toks)):
            s, e = toks[a][0], toks[b][1]
            if e - s > 500:
                break
            yield sentence[s:e]
            trimmed = sentence[s:e].rstrip(".,;:!?\"”’)")
            if trimmed and trimmed != sentence[s:e]:
                yield trimmed


def prose_of(served_text: str) -> str:
    """The page's prose (§4 Pages): drop header lines up to the first empty line."""
    lines = served_text.split("\n")
    if lines and re.match(r"^[A-Z][a-z]+(-[A-Z][a-z]+)*: ", lines[0]):
        for i, ln in enumerate(lines):
            if ln.strip() == "":
                return "\n".join(lines[i + 1:])
        return ""
    return served_text


def evidence_values(texts, field: str, domain: str) -> set:
    """Every value some excerpt (sub-span of one sentence of the prose texts) supports."""
    out = set()
    for text in texts:
        for sent in sentences(prose_of(text)):
            if not names_company(sent, domain):
                continue
            for sp in spans(sent):
                out |= {next(iter(v)) for v in [supported_values(sp, field, domain)] if len(v) == 1}
    return out


def sentence_values(texts, field: str, domain: str) -> set:
    """Values supported by a whole sentence of some text's prose."""
    out = set()
    for text in texts:
        for sent in sentences(prose_of(text)):
            v = supported_values(sent, field, domain)
            if len(v) == 1:
                out |= v
    return out


# ---- stage 4: investors (stage-4.md Investors)
def cap_runs(seg: str):
    """[(start, end, [words])]: maximal runs of capitalised words (A.4) joined by single spaces."""
    toks, i, n = [], 0, len(seg)
    while i < n:
        if alnum(seg[i]):
            j = i
            while j < n and alnum(seg[j]):
                j += 1
            toks.append((i, j))
            i = j
        else:
            i += 1
    runs, cur = [], []
    for s_, e_ in toks:
        w = seg[s_:e_]
        if is_cap_word(w):
            if cur and seg[cur[-1][1]:s_] == " ":
                cur.append((s_, e_))
                continue
            if cur:
                runs.append(cur)
            cur = [(s_, e_)]
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return [(r[0][0], r[-1][1], [seg[a:b] for a, b in r]) for r in runs]


def investor_names(excerpt: str, domain: str) -> set:
    """The investor names an excerpt supports: rules 1 to 4 of A.2 (single sentence, names the company, a
    statement phrase for investors, no negating phrase), then every investor name it contains."""
    t = collapse(excerpt)
    if not (1 <= len(t) <= 500) or not is_single_sentence(t) or not names_company(t, domain):
        return set()
    if not any(has_phrase(t, p) for p in PHRASES["investors"]) or any(has_phrase(t, n) for n in NEGATING):
        return set()
    chars = list(t)
    for p in [name_of(domain)] + PHRASES["investors"]:
        for s_, e_ in find_words(t, p):
            for k in range(s_, e_):
                chars[k] = "\x00"
    c = "".join(chars)
    runs = cap_runs(c)
    names = {c[s_:e_] for s_, e_, ws in runs if len(ws) >= 2 and ws[-1] in INVESTOR_LAST}
    if amounts(t):
        for p in ("led by", "backed by"):
            for _, e_ in find_words(t, p):
                if e_ < len(c) and c[e_] == " ":
                    for s_, e2, ws in runs:
                        if s_ == e_ + 1:
                            names.add(c[s_:e2])
    return names
