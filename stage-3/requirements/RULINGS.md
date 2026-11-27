# RULINGS (stage 3: rulings 1-55 carried from stages 1-2 and still apply unless 56+ says otherwise; 56+ are new)

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
26. **A dossier named `www.x` (from `www.www.x`) is not addressable by path (ruled).** §4 normalisation
    is not idempotent: the POST response and the list carry `www.x`, `GET /dossiers/www.x` normalises to
    `x` and gives 404. Accepted as spec-consistent; tests only check POST 202 + list; export/import of such
    a dossier must work (§10).
27. **`null` for a required body field (ruled).** `null` is a JSON type other than string, so
    `{"domain": null}` is 400 `malformed_request` (wrong type), preferred; 422 is tolerated by the test.
28. **Empty or whitespace-only body (ruled).** Not valid JSON: 400 `malformed_request` on every endpoint
    that reads a body (signup, login, POST /dossiers, reset, clock, import); `POST …/refresh` ignores
    any body. Tests assert 400 strictly. Auth (401) still comes first on authenticated routes.
29. **Implementer rulings (reviewed).** (1) non-whole-dollar amount / decimal headcount ignored rather
    than disqualifying the excerpt: *rejected as a reading of A.2.5* only if it makes a mixed sentence
    (e.g. `raised $0.0000005 million and $3M`) supported for 3 M — but §A.5 says such an amount "is not a
    value", so it is not a value of the sentence and cannot conflict: **accepted**. A headcount with a
    decimal part (`12.5 people`) is not a headcount value either (A.4 "no decimal part"): **accepted**.
    (2) whole-sentence citations only: **accepted** (strictly safer; RULINGS 1–2). (3) four digits, no comma:
    **accepted** (RULINGS 8). (4) empty body = {}: **rejected**, see 28. (5) null = missing: see 27.
    (6) export during a build → after import `failed`, all unknown, spent 0 when no build had completed:
    **accepted** ("holds the dossier as it was before that build"). (7) mock-mode 6 s window / live 45 s,
    150 s, 285 s: accepted for BD-4/BD-5 (live ≥30 s per call, ends <300 s); Reviewer inspects.

## Stage 2

30. **Rulings 1 and 6 are superseded where the selection rule decides (T).** Stage 1 accepted any supported
    value; stage 2 fixes the selected value by the rule. Tests compute, from the corpus and the independent
    Appendix A oracle, every value each *evidence page* supports (whole sentences of the page's browser text)
    and assert: candidates ⊇ that set, candidates ⊆ that set ∪ fragment-only values, and — when a field has
    no fragment-only value possible — the exact candidate order, selected value and status. Fragment-only
    candidates (ruling 1's F) are tolerated, never required, and never asserted exact.
31. **One candidate per (page, value) (T).** "Once for each such page": two sentences of one page stating the
    same value are one candidate (excerpt: either); one page stating two values gives two candidates with the
    same `url`; the same page served by two providers is still one candidate (`provider`: any that served it).
    Candidate identity is therefore (url, value); no test requires a particular excerpt or provider except
    that the provider named served the excerpt (and, for rendered pages, text of the browser).
32. **Evidence pages (T, as ruling 4).** Searchable pages of the corpus (every company has <= 8 pages, so one deep
    search or the lite searches plus extracts reach them) plus every page a nimble research claim cites —
    supported or not. A page nothing but research points at (`searchable: false`) must be read (extract/render):
    the claim's own excerpt is not the page. The graded corpus differs; the principle does not.
33. **Page text is the browser text (T).** In the corpus, a page's `text` is what a browser shows and `static_text`
    is what search and extract serve (stale, empty or different). A value only the static text supports is not
    a candidate and an excerpt only in the static text is not a valid citation or candidate excerpt; a value
    only the browser text shows must be found: the build must use Nimble's rendered extract (cost 3 per URL) or
    a browser vendor. Disclosure controls (ruling by the spec: "graded corpus contains none") are not tested.
34. **`Kind` matching is exact (T for the cases tested).** `own`, `filing`, `news`, `aggregator`, lower case. Tests
    use clearly unlisted values (`blog`) and absent lines; case variants (`OWN`) and header spacing are
    unspecified and untested. A listed `Kind` wins over the host rule in both directions (`Kind: own` on a third-
    party host is own; `Kind: news` on the company's host is news).
35. **Host rule (T).** "normalised as stage-1.md normalises a domain": `www.` stripped, lower-cased, trailing dot
    removed; `blog.<domain>` is another host (aggregator). A URL's port or user-info is not tested.
36. **`Published` validity (T for the cases tested).** RFC 3339 `date-time`: `T`, time, explicit offset (`Z`
    or ±hh:mm), optional fraction. A date alone, a time without offset, words and an impossible calendar date
    (`2026-02-30T00:00:00Z`) are not timestamps: no publication time. Lower-case `t`/`z` and a space separator
    are unspecified and untested. `published_at` may be written with any offset; tests compare instants.
37. **Recency compares instants (T).** `2026-01-10T00:00:00Z` and `2026-01-10T01:00:00+01:00` are equal (tie);
    fractions count. Ties fall through to the URL, compared as the page's URL string by code point
    (`/About` < `/about` < `/about/`); a URL is not normalised for this.
38. **Value order (T).** Same URL and provider: integers numerically (9000000 before 10000000), strings by code
    point after trimming (`Zagreb` before `Århus`; no locale collation, no case folding).
39. **Provider tie-break (M).** Not observable through the API (a page is one candidate per value whatever the
    provider); checked only on the offline model (test_02).
40. **`retrieved_at` (T).** Equal to the dossier's `researched_at` for every candidate (the candidates are those of the
    last ready build, gathered at its time); during a later running build still the last ready build's.
41. **Imported candidates have a null `kind` and the authority of `aggregator`** (stage-2.md "Only an imported
    candidate has a null kind"). Tests accept `kind`/`published_at` either null or equal to the page's (the stage-1
    export may or may not record them) and check the ranking, `selected`, `value`, `status`, `citations` only
    as the rule gives them for the candidates *as reported*.
42. **Imported candidate set (T).** Equal to the values supported by whole sentences of every text the mock logged as
    served (search snippets and bodies, extract pages, research excerpts) to the stage-1 build that was the last to
    complete `ready`. The test corpus keeps pages under 300 characters so no truncated text creates a fragment.
    A stage-1 dossier that never completed is `failed`, all fields unknown, `candidates: []` (§10).
43. **Upgrade of a "signed-in browser" (T).** Stage 1 has no screens, so "signed in before" is exercised twice:
    (a) the token the client held on the stage-1 service is valid on the stage-2 service after importing the
    stage-1 export (API); (b) a browser signed in through the stage-2 UI is still signed in after the same service
    exports and re-imports its state, with no page reload (UI). A lost request is likewise exercised by (a)
    replaying the stage-1 key/body against stage 2 (200, the original body, no provider call) and (b) in the UI.
44. **A 429 is retried (T).** The spec says a call that was refused is answered normally at the latest on the fourth
    attempt and that waiting does not count toward 10 s, so a build that gives up on a 429 is wrong. Tests: nimble
    refuses the first attempt of every call (`throttle`) or three in a row (`rate_limit`), tavily down: the
    build ends `ready` with the exact candidates, no cost for refused calls, `spent_units` = logged costs.
    Time bound for `throttle`: 10 s + 3 s per refused call + 2 s (the length of a service's wait is its choice).
    A service that retries sooner than 1 s after a refusal is answered 429 again by the mock: allowed.
45. **Browser vendors are optional (T).** `kernel`/`browserbase` failing (500) must not change any result; sessions
    leaked beyond 4 are visible only through behaviour (concurrent builds stay exact); releasing sessions is a
    Reviewer inspection (S2-WEB-4).
46. **Stage-1 CO-8 ("an extract through nimble does not set `render`") is superseded.** A nimble extract costs
    1 or 3 per URL (rendered); a tavily extract 2 per URL; spend must equal the logged costs.
47. **HTML routes (T).** `GET` with `Accept: text/html` and no token returns 200 `text/html` for the six routes (a
    browser navigation carries no bearer). An unknown dossier's browser route is 200 or 404 with HTML and shows
    `dossier-not-found`. The same URL with no `Accept: text/html` is the API: 401 without a token, 404 JSON when
    unknown. Behaviour of the UI routes for a signed-out browser (redirect to /login or a prompt) is unspecified
    and untested, except `/login` and `/signup` themselves.
48. **UI element placement (L).** Tests locate by `data-testid` only; `dossier-list`/`contested-list` items may be nested
    (tests check document order and containment, not direct-child-ness). A "formatted" value is the UI's choice:
    tests require that the text shows the value in a recognisable form (money as `$12M`, `12 million`, `12,000,000`;
    headcount ranges with `-`, `–`, `—` or `to`), that a year has no thousands separator, that nothing prints
    `null`/`undefined`/`[object`, and that no raw RFC 3339 timestamp is on a screen.
49. **`contested-item` text (L).** "contains the field": the field key (`founded_year`) or its words (`founded year`),
    case-insensitively; "every distinct candidate value" in a recognisable form as above.
50. **Retry in the UI (T).** "Retryable with the same key and body" means: after `*-uncertain` the user activates the
    same submit/refresh control again, with the form unchanged; tests observe the `Idempotency-Key` header and
    JSON body of every POST and require them identical. The retried request is answered 200 (replay of a
    committed request) or 202 (the first never arrived); both are success.
51. **Polling cadence (T).** Reads of a `building` dossier are any GET of `/dossiers/{domain}` (fetch, XHR or
    navigation) seen by the browser: at least 3 in the build window and no gap above 2.6 s (2 s + slack); the final
    state is shown within 3.5 s of the API reporting it.
52. **Latest-read-wins (T, with an escape).** The browser's read response is held (the server has answered) while a
    later read completes and then released; the screen must show the later data. When the UI does reads by
    navigation, or disables `dossier-reload` while a read is pending, no out-of-order response is possible: the test
    then asserts the sequential outcome. The same is done for the first read of a `building` dossier.
53. **Product-quality checks are heuristics (T(heuristic) + UX seat).** No horizontal scroll (`scrollWidth` <=
    `clientWidth`) at 375 and 1280 px on every route; every visible text/control meets WCAG AA contrast measured
    from computed colours (elements over background images are skipped); a keyboard-focused control changes
    outline/box-shadow/border/background; visible `<label>` for every input; distinct computed colours for field
    statuses (known/contested/unknown), dossier states (building/ready/failed) and refused vs uncertain; each
    citation shows its excerpt in `blockquote`/`q` or between quotation marks and links to its exact URL.
    Subjective rows (S2-PQ-12, S2-PQ-13 and the finer points of S2-PQ-5/8/9/10) are for the UX reviewer.
54. **Not tested (recorded).** S2-TX-4 (statement about the graded corpus), S2-WEB-5 (env/`provider_config` use:
    Reviewer reads the code), S2-SEL-11 (provider tie-break; offline model only), the 60-second session reaping of
    a provider, unauthenticated-browser redirects, and a UI served client- vs server-side.
55. **What the stage-1 export can carry (T, ruled by evidence and confirmed by the Coordinator).** The team's final stage-1 service exports, per
    dossier, only the selected value and its citations (inspected: the export holds no other served text; e.g. the
    aggregator page that a build was served never appears in it) and imports make no provider call (§10). The
    sentence "each imported field gains one candidate for every value that text the providers served [...]
    supports" can therefore be met only for what the export records. The tests demand: every exported citation is
    a candidate (same url, value, excerpt, provider, `retrieved_at` = `researched_at`); no candidate that the served
    text does not support; every supported (page, value) of a page the export mentions is a candidate; value,
    status, citations, order and `selected` follow the rule. They do **not** demand candidates from pages the export
    never mentions, and a stage-1 dossier therefore imports as `known` wherever stage 1 kept one value. The hidden
    upgrade check may expect more than this export allows; that cannot be satisfied by the stage-2 service alone.

## Stage 3 (56+)

56. **The corpus's `true_from` is the `Effective` header, verbatim (T).** The mock writes a page's `true_from` as the line
    `Effective: <value>` and `published_at` as `Published: <value>`, both verbatim, so tests can serve invalid ones. A
    "valid `Effective` line" is `YYYY-MM-DD`, four-two-two digits, that is a real calendar date (2026-02-30 and 2023-02-29 are
    not; 2024-02-29 is; `2026-3-1` and a timestamp are not). An invalid line is as if absent and `Published` decides.
57. **`published_at` to a date (T).** A valid RFC 3339 `Published` (explicit offset) converted to UTC, date part
    (`2026-02-10T23:30:00-05:00` is 2026-02-11). An invalid `Published` counts as no `Published`: `true_from` null.
58. **Selected value's `learned_at` (T).** "The time of the build that made it the selected value" is read as the build
    that added the field's latest history entry (the build that changed the selected value to the value now selected). A
    later build with the same selected value (candidates, citations, `true_from` different) leaves `learned_at`
    unchanged while the field's `true_from` is the *current* selected candidate's; the history entry keeps the dates it was
    made with. A value that disappears and comes back is learned again at the build that brings it back.
59. **Candidate `learned_at` and the provider (T).** The identity (field/title, value, URL, provider) includes the provider,
    which stage 2 lets the service choose among providers that served the text. Tests therefore compute the expected
    `learned_at` from the candidate sets the service itself returned after each build (earliest ready build whose set held
    the same (field, title, value, URL, provider)), and check `retrieved_at` = the build's time. They never demand a provider.
60. **`as_of` strict form (T).** RFC 3339 `date-time` with seconds, `T` (or `Z`) and `+hh:mm`/`Z` offset, optional fraction.
    Rejected with 422: no offset, a date alone, a number, an empty value, a space instead of `T`, an offset without colon is
    not tested, month 13, hour 25, `2026-04-31`, `...T09:00Z` (no seconds). Valid but unusual forms (`Z`, fractions,
    other offsets) are instants and compared as instants. An `as_of` equal to a build's time includes it.
61. **`true_at` strict form (T).** `YYYY-MM-DD` that is a real date (leap days accepted, 2025-02-30 and `2025-6-1` 422); a
    timestamp is not a date. Missing or empty is 422. `true_at` compares as a date with `true_from`; a version holds on the
    date `true_from` itself.
62. **What a build "gathers" (T for pages with candidates and research-cited pages).** Stage 2 already requires every page of
    the evidence with a supported value to yield its candidates and a research-cited page to be read, so those URLs are
    surely gathered. The stage-3 corpus therefore puts the "version with no candidates" on a page that is `searchable: false` and
    cited by the research claim (meridian-ledger `/leadership`, epoch 3), never on a page whose reading a service may skip.
    A URL not gathered by a later build keeps its versions (nothing ends them); tests assert this (S3-VA-3), including
    that a vanished aggregator page still holds at `/values` while the dossier itself has no value from it.
63. **Versions of one build per URL (T).** The model: ready builds with time <= `as_of` in build order; a version with
    `true_from` t replaces earlier versions of its URL with `true_from` >= t (all of them when t is null); the latest
    survivor ends on t. Equal times: the later build in build order. A version with null `true_from` holds on no date.
    Authority/recency of a candidate at `true_at` is that of the candidate's own page version (`published_at`), exactly as in
    a build.
64. **`as_of` answers are immutable and exact (T).** The response equals the dossier right after that build (fields with
    their candidates and both times, `researched_at`, `dossier_id`), with `state` `ready` and `spent_units` the total of all
    builds (ready or failed) whose time is at or before `as_of`; tests compare the JSON equal, not just selected values.
    `GET` without `as_of` after the last build equals `as_of` far in the future.
65. **Executives (T).** Members are the titles that have candidates, ranked per title by the stage-2 rule (names by code point
    as the last tiebreak); `candidates` are grouped cfo, coo, cto then rank order; status contested when any title has two or
    more names (aggregator and own page); `true_from` null when any member's is null; `learned_at` of the field is that of
    its latest history entry like any field (ruling 58). When the evidence for a title could be read from a fragment of a
    sentence that Appendix A rejects as a whole (two names in one sentence), a fragment candidate is tolerated, never
    required (as ruling 1/2); the stage-3 corpus keeps the timeline companies free of such sentences so selection is exact;
    paxton-quay.test carries them and is checked tolerantly (candidates between "whole-sentence" and "fragment" sets).
66. **Typing of executives and equal dates (T).** "On or before" includes equal dates: a new value whose `true_from` equals the
    earlier one is a `correction` (both non-null). An executives entry is typed by the titles that differ (one side has the
    title, or names differ); a title that appears or disappears is never a correction. All members of one page share the page's
    `true_from`; a title read from another page has that page's.
67. **Imported dates (L for the Effective line).** The stage-1/stage-2 exports are implementation-defined. The tests demand:
    imported candidates `learned_at` = `retrieved_at`; the history initial entry `learned_at` = `researched_at`; `true_from`
    either null (stage-1; the spec says "null unless the exported state records the dates") or equal to the date of the candidate's
    recorded `published_at`/the page's Effective; for a stage-2 export (which records the builds' served candidates) each candidate's
    `true_from` is the date given by the page's Effective (if the export kept the line) or by its Published, and null when neither.
    Tests accept either reading where the page has both lines, and use only pages and `true_at` values at which both readings agree for
    the `/values` cases.
68. **An `as_of` response of an imported older stage-2 build (L).** The spec says an `as_of` response "takes each field's `learned_at`
    and `true_from` from that history" for imported state, and the imported history has one entry per field with `learned_at`
    = `researched_at` (the last build). Tests demand that rule only for `as_of` at the last imported build's time; for earlier
    imported builds they demand value, status, citations, candidates, `researched_at`, `spent_units` as the stage-2 service had them,
    and candidate `learned_at` per the first-build rule.
69. **First build after import (T).** The comparison is with the imported selected values (and their `true_from`): for stage-1 and
    stage-2 state `executives` was unknown, so the first build with a value adds a `change` (never `initial`, the dossier's first
    ready build being the imported one).
70. **Restarts need an external kill (T via RESTART_CMD).** The black-box harness cannot stop a container; `run.sh` provides
    `RESTART_CMD` (`docker kill` = SIGKILL, then `docker start`, same container filesystem, fixed host port) and the tests wait for
    `/health` themselves (<= 120 s). When `RESTART_CMD` is not set (e.g. `run_against.sh` on a bare process) the restart tests are
    skipped and S3-RS-* stay open. The kill is made right after the last response (no settle time). "When no build is running" is
    arranged by waiting for `ready`.
71. **Clock after restart (T).** After a restart the next build's `researched_at` (no clock call between) is the clock value that
    was set before the stop. The clock at reset (fixture `now`) or at `POST /_test/clock` is the last value set; the system clock
    does not advance it (stage 1 CK-2).
72. **Concurrency (T).** "Same results as one at a time in some order": 6 dossiers x 8 simultaneous refreshes with readers on every
    new endpoint; checked: one build per dossier (exactly one domain-query search each), each history list grows by one, the feed has exactly
    one entry per dossier, seq unique and increasing, every feed page seen by a reader is a consistent prefix of the final feed.
73. **Not testable black-box (recorded).** S3-RS-7 (state on the container filesystem, no volume): the harness runs the container without
    a volume, and the restart tests are the evidence; a Reviewer inspection of the Dockerfile/state location backs it. S3-DEP-1:
    run.sh builds the stage-3 image alone and RUN.md is read by the Reviewer.
74. **Selection rule carried (T).** All stage-1 and stage-2 acceptance tests are carried forward and adapted only where the seventh
    field and the two times change an exact shape (`UNKNOWN` field shape, "all fields known" restricted to the six fields). The
    carried tests ignore `executives` except where a corpus company has executive sentences (checked tolerantly in `check_exec_candidates`).

