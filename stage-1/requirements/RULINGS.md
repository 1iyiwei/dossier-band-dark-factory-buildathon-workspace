# RULINGS (stage 1)

Ambiguities found in the specification, the reading the band adopts, and why. Tests encode
these readings; a rule marked **T** is asserted, **L** means tests are deliberately lenient.

1. **Support is judged on whole sentences for "known", on strict Appendix A for citations (T).**
   §4 lets an excerpt be any 1–500 character substring of a sentence, so a fragment can drop a
   negating word (`Former CEO Rosa Alvarez left X` → `CEO Rosa Alvarez left X`). Tests label each
   corpus field **K** (some whole sentence supports a value: field must be known, value from the
   listed set), **U** (no sentence *and no fragment* supports anything: must be unknown) or **F**
   (only a fragment supports a value: known or unknown both accepted). Every citation of every
   known field, whatever the label, must satisfy Appendix A literally (oracle.py).
2. **Context-faithful citations (T).** A citation whose excerpt lies inside a sentence that
   contains a negating phrase is rejected even if the fragment alone satisfies A.2 (it would
   attach a value to a claim the page hedges or negates: §1 "attached to a value it does not support").
3. **An excerpt may cross a line break (L).** Whitespace runs, newlines included, may be written
   as one space (§4), and A.1's single-sentence test applies after that; so `Priya` / `Nair.` on two
   lines can be cited as `…is Priya Nair.`. Such fields are labelled F.
4. **Evidence = prose of every page a search returns + nimble research claims (T).** Pages that no
   search returns (`searchable:false`) count only through a research claim whose citation supports
   it, so research-only facts (kestrel-freight ceo, funding) must be known: the service has to run
   the research. The corpus keeps every company within one deep search (≤8 searchable pages) so
   the 80-unit budget never prevents gathering; failing to find evidence is therefore a defect.
5. **Research excerpts are "served text" (T).** The research citation snippet counts as text a
   provider served for the page at `url`, with provider `nimble`; the excerpt cited must be a
   substring of a snippet or of any text served for that URL by the provider named in the citation.
6. **Contradicting sources (T for the mechanics, L for the choice).** When several values are
   supported (aggregator vs own site, partial vs total funding) any supported value is accepted
   (§4: "holds one of them"); nothing prefers the company's own site. Stage 1 has no authority rule.
7. **A value of another kind that Appendix A accepts is accepted (T).** `headquartered in
   Scandinavia` supports `hq_city = Scandinavia`; `Stoke-on-Trent` yields `Stoke` (A.4: capitalised
   words joined by `-`: `on` is lower case). The spec says it decides support "by these rules alone".
8. **"Exactly four digits" (A.4 founded_year)** means four digit characters, no `,`/`.` separators; no
   fixture depends on `1,900`.
9. **`Z` is an explicit offset (T).** RFC 3339 `Z` is accepted in responses; the tests parse instants,
   they do not compare strings.
10. **Idempotent replay of a first-use that answered 202** returns 200 with the *original 202 body*
    (`state: building`), even after the build ended (§7).  A request that answered 200 (existing
    dossier) replays as 200 with the same body.
11. **Different path ⇒ different request (T).** A refresh on `Acme.test` and on `acme.test` with the
    same key are two first uses (both 202, same running build); repeating either is the replay (200).
    `POST /dossiers` with the same key and the domain spelled differently is a different *body*: 409.
12. **Order of checks (T where stated, otherwise untested).** 401 first (even with a missing key,
    bad body); then body must parse as a JSON object (else 400); then a claimed key (409 for another
    body, replay 200); then required-key, key length, field validation. Missing key combined with an
    invalid body is unspecified and untested.
13. **Integer query parameters (T).** Plain decimal digits only; leading zeros (`05`) are digits and
    accepted; an empty value (`limit=`) is not digits: 422. `q=` (empty) lists everything.
14. **`q` is a literal substring match (T)**, not a pattern: `%`, `_`, `.`, `*`, `(` match only themselves.
15. **Wrong-type bodies on control endpoints (L).** Import with `track:5`, `format_version:"1"`,
    `state` not an object, or a non-object body may be 400 (wrong type, §5) or 422 (§10); both pass.
    Missing fields, wrong track, wrong version number: 422 only. Nothing may change on rejection.
16. **Clock body (T).** Missing `now`: 422; wrong JSON type for `now`: 400; no offset/garbage: 422;
    an instant equal to the current one is accepted; "earlier" compares instants across offsets.
17. **Provider timeouts and cost (T proxy + R).** Against the mock a delay fault of 3 s is used.
    Whatever the service does (wait, or time out) its `spent_units` must equal the sum of the costs
    the mock logged for the calls (timeouts count, §9). The 30 s / 120 s / 300 s live-provider
    patience rules cannot be exercised offline: the Reviewer inspects the timeouts in the code (BD-5).
18. **"Exactly one search for the domain" under errors (T, bounded).** Nominal and
    fully-retried builds must have exactly one successful domain-query search; when the provider
    refuses searches (500/429/throttle) at most one is asserted, because no success may be possible.
    Searches the provider refuses cost 0 and are not counted.
19. **A company with no evidence ends `ready`, not `failed` (T).** `failed` means no provider call
    succeeded (§8); a successful search that finds nothing about the company gives all fields
    unknown with `researched_at` set.
20. **`spent_units` while a build runs** is monotone non-decreasing and ≥ the previous build's total;
    its exact value mid-build is not asserted.
21. **Pre-reset clock (T on a fresh second instance only).** Verified with `BASE_URL_2`, before it is reset.
22. **Domain in a path (T).** Percent-decoded, then normalised (whitespace trimmed, `www.` etc.); an
    invalid result (`https://x`, `www.test`, `a_b.test`) is 422, evaluated before 404.
23. **Unknown routes/methods (L).** 404 or 405, both with the §5 error envelope; the `code` is not asserted.
24. **Mock traits in this corpus** are noise 0 / rate_limit 0 (`corpus/traits.json`); the graded
    corpus has other draws, so tests do not depend on provider ordering.
25. **Email normalisation, `a@b` as an address, duplicate emails differing only in case, and a
    whitespace-only `display_name`** are unspecified: not tested.
