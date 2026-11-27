# LEDGER (stage 2: stage-1 rows carried forward, then S2-* rows)

Kinds: T acceptance test (`requirements/acceptance`), RUN run.sh measurement, R review inspection, M measurement. Status: open / passing / failing / ruled.

| ID | § | Requirement (quoted) | Verification | Status |
|---|---|---|---|---|
| DEP-1 | §2 | Deliver an HTTP service, a `Dockerfile` and a `RUN.md` with a command that builds and starts the service without manual setup. | RUN+R | passing (test/run); R part open: Reviewer inspection |
| DEP-2 | §3.1 | Listen on `0.0.0.0` using the `PORT` environment variable, default `8080`. | RUN | passing (run.sh) |
| DEP-3 | §3.2 | Return 200 once the service and its data store can serve requests, within 60 seconds of container start. | RUN | passing (run.sh) |
| DEP-4 | §2 | CPU \| 2 vCPU; Memory \| 3 GiB; Concurrent requests \| up to 50 in flight (run.sh limits the container to 2 CPU / 3 GiB and runs the load tests) | RUN | passing (run.sh) |
| DEP-5 | §2 | The image must run on its own with `-e PORT=<port>` and a port mapping. All runtime dependencies, initialization and seed data must work within that single container. | RUN+R | passing (test/run); R part open: Reviewer inspection |
| DEP-6 | §2 | The stage folder's dependency manifest lists `webrouter>=0.12.0`. | R | open: Reviewer inspection |
| DEP-7 | §2 | every request to a provider goes through `web_router`: called in-process, or from a Python helper process that the service runs inside its own container. [...] Calling a provider's API by any other route is not permitted. | R | open: Reviewer inspection |
| DEP-8 | §2 | Tavily is optional: a service may use it beside Nimble, and its absence must not prevent research while Nimble answers. | T — test_faults.py | passing |
| DEP-9 | §2 | at run time, **only the provider endpoints this specification lists** [...] Runtime assets and dependencies must be included in the image. | R | open: Reviewer inspection |
| H-1 | §3.2 | GET /health -> 200 {"status": "ok"} | T — test_auth.py | passing |
| H-2 | §3.2 | `/health` makes no provider call. | T — test_api.py | passing |
| R-1 | §3.3 | When reset returns 204, subsequent requests must see only that fixture: no users other than the seeded ones, no dossiers and no stored idempotent responses. | T — test_auth.py, test_faults.py | passing |
| R-2 | §3.3 | Repeated resets are supported. | T — test_auth.py | passing |
| R-3 | §3.3 | A build still running when reset is called must not change the state that follows the reset. | T — test_faults.py, test_state.py | passing |
| R-4 | §3.3 | This control endpoint must be enabled in the delivered image and requires no authentication. | T — test_auth.py | passing |
| R-5 | §4 | A fixture with two users sharing an email is a reset error: 422 `validation_failed`, changing nothing. | T — test_auth.py | passing |
| R-6 | §4 | `now` is required and sets the clock (§3.4). | T — test_auth.py | passing |
| R-7 | §4/§6 | Seeded users must be able to log in with the given password immediately. / For a user seeded by the fixture (§3.3), `user_id` is that user's `id` in the fixture. | T — test_auth.py | passing |
| CK-1 | §3.4 | Reset sets the clock to the fixture's `now`. | T — test_state.py | passing |
| CK-2 | §3.4 | The clock stands still between calls: two requests with no clock call between them read the same time. | T — test_state.py | passing |
| CK-3 | §3.4 | A `now` earlier than the clock's current time is 422 `validation_failed` and changes nothing. | T — test_auth.py, test_state.py | passing |
| CK-4 | §3.4 | `POST /_test/clock` requires no authentication. (-> 204 No Content) | T — test_auth.py | passing |
| CK-5 | §3.4 | `now` is an RFC 3339 timestamp with an explicit offset. | T — test_auth.py | passing |
| CK-6 | §5 | Reserve 400 `malformed_request` for a body that does not parse or a field of the wrong type. (applied to the clock body) | T — test_auth.py | passing; ruled (see RULINGS 26-28) |
| CK-7 | §3.4 | Every timestamp the service records or returns is read from this clock. | T — test_builds.py, test_state.py | passing |
| CK-8 | §3.4 | Before the first reset the clock follows the system time. | T — test_00_fresh_clock.py | passing |
| CV-1 | §3.5 | Requests and responses are `application/json; charset=utf-8`. | T — test_auth.py | passing |
| CV-2 | §3.5 | Unknown fields in a request body are ignored, never an error. | T — test_api.py, test_auth.py | passing |
| CV-3 | §3.5 | Unknown query parameters are ignored. | T — test_api.py | passing |
| CV-4 | §3.5 | IDs are opaque strings of at most 64 characters. | T — test_api.py, test_auth.py | passing |
| CV-5 | §3.5 | Timestamps in responses are RFC 3339 with an explicit offset | T — test_api.py | passing |
| CV-6 | §5 | Every 4xx and 5xx response carries this body: { "error": { "code": "not_found", "message": "..." } } | T — test_auth.py | passing |
| CV-7 | §5 | 400 `malformed_request`: Unparseable body, or a field of the wrong JSON type | T — test_auth.py | passing; ruled (see RULINGS 26-28) |
| CV-8 | §5 | An integer-valued **query parameter** is written as plain decimal digits: `1e9`, `4.0` and `+4` are 422 `validation_failed` whatever their numeric value. | T — test_api.py | passing |
| CV-9 | §5 | `Idempotency-Key` 1 to 255 characters; `limit` integer 1 to 200; `offset` integer 0 or more; otherwise 422 `validation_failed` | T — test_api.py | passing |
| CV-10 | §5 | Requests must not produce 5xx responses, including under concurrent load and when a provider endpoint answers with an error. | T — test_concurrency.py, test_s2_api.py | passing |
| CV-11 | §2 | Per-request timeout \| 5 s (10 s for `POST /_test/reset`) | T — test_concurrency.py | passing |
| AU-1 | §6 | POST /auth/signup -> 201 { "user_id": "u_1", "display_name": "Ada", "token": "..." } | T — test_auth.py | passing |
| AU-2 | §6 | POST /auth/login -> 200 { "user_id", "display_name", "token" } | T — test_auth.py | passing |
| AU-3 | §6 | Email already registered \| 409 `email_taken` | T — test_auth.py | passing |
| AU-4 | §6 | Password shorter than 8 characters \| 422 `validation_failed` | T — test_auth.py | passing |
| AU-5 | §6 | `email` not of the form `local@domain` \| 422 `validation_failed` | T — test_auth.py | passing |
| AU-6 | §6 | `display_name` empty or longer than 100 characters \| 422 `validation_failed` | T — test_auth.py | passing |
| AU-7 | §6 | Wrong password or unknown email on login \| 401 `unauthenticated` | T — test_auth.py | passing |
| AU-8 | §6 | Every other endpoint requires a bearer token, except `/health`, the `/_test/*` endpoints and the two above. | T — test_auth.py | passing |
| AU-9 | §6 | A request to such an endpoint that lacks a valid token is 401 `unauthenticated`, even when it also lacks a required `Idempotency-Key`. | T — test_auth.py | passing |
| AU-10 | §6 | Tokens do not expire. An account may have multiple valid tokens and concurrent sessions. | T — test_auth.py | passing |
| AU-11 | §6 | Passwords must be stored using a password-hashing function such as bcrypt, scrypt or Argon2, or an equivalent. Plaintext password storage is not permitted. | T+R — test_state.py | passing (test/run); R part open: Reviewer inspection |
| AU-12 | §5 | 401 `unauthenticated`: Missing, malformed or unknown bearer token | T — test_auth.py | passing |
| AU-13 | §6/§5 | A required field or query parameter is missing [...] 422; a field of the wrong JSON type 400 (signup/login bodies) | T — test_auth.py | passing |
| AU-14 | §6/§11 | Email already registered \| 409 `email_taken` (under concurrent signups: results as one-at-a-time) | T — test_auth.py | passing |
| DM-1 | §4 | Every domain the API takes, in a body or a path, is first **normalised**: surrounding whitespace removed, lowercased, one trailing `.` removed, and one leading `www.` removed. | T — test_api.py | passing |
| DM-2 | §4 | The normalised domain must then be a valid host name: two or more labels separated by `.`, each label 1 to 63 characters of `a-z`, `0-9` and `-`, not starting or ending with `-`, and 253 characters or fewer in total. Anything else, including a URL with a scheme or a path, is 422 `validation_failed`. | T — test_api.py | passing |
| DM-3 | §4 | `Acme-Robotics.TEST.`, `www.acme-robotics.test` and `acme-robotics.test` name the same company and the same dossier. | T — test_api.py | passing; ruled (see RULINGS 26-28) |
| DM-4 | §4 | Responses always carry the normalised domain. | T — test_api.py | passing |
| DM-5 | §4/§8 | The domain in the path is normalised (§4). [invalid -> 422] | T — test_api.py | passing; ruled (see RULINGS 26-28) |
| PD-1 | §8 | 202 { "dossier_id": "d_7", "domain": "acme-robotics.test", "state": "building" } (new dossier: creates it and starts its first build) | T — test_api.py | passing |
| PD-2 | §8 | When a dossier already exists for the domain, the service starts no build and returns **200** with that dossier's `dossier_id`, `domain` and current `state`. | T — test_api.py | passing |
| PD-3 | §8 | `domain` missing \| 422 `validation_failed`; `domain` invalid after normalisation \| 422 `validation_failed` | T — test_api.py | passing; ruled (see RULINGS 26-28) |
| PD-4 | §5 | 400 `malformed_request` for a field of the wrong JSON type (`domain` not a string) | T — test_api.py | passing; ruled (see RULINGS 26-28) |
| PD-6 | §8 | Concurrent requests for the same domain create one dossier and start one build, whatever their keys. | T — test_concurrency.py, test_idempotency.py | passing |
| PD-7 | §8 | [POST /dossiers for an existing domain] starts no build (no provider call) | T — test_api.py | passing |
| GD-1 | §8 | `fields` always holds all six fields. [with value/status/citations shape; types per §4 table] | T — test_api.py | passing |
| GD-2 | §8 | `state` is `building` while a build runs, otherwise the outcome of the latest build, `ready` or `failed`. | T — test_api.py | passing |
| GD-3 | §8 | Before the first build completes `ready`, every field is `unknown`. | T — test_api.py | passing |
| GD-4 | §8 | While a later build runs, `fields` are those of the last build that completed `ready`. | T — test_builds.py, test_concurrency.py, test_faults.py | passing |
| GD-5 | §8 | `researched_at` is the time of the last build that completed `ready`, or null. / A build's **time** is the clock's time when the request that started it was received. | T — test_builds.py, test_faults.py, test_state.py | passing |
| GD-6 | §8 | `spent_units` is the total cost (§9) of every provider call made for this dossier, by every build, since it was created. | T — test_builds.py | passing |
| GD-7 | §8 | The domain in the path is normalised (§4). No dossier for it is 404 `not_found`. | T — test_api.py | passing; ruled (see RULINGS 26-28) |
| GD-8 | §4 | Every authenticated user sees the same dossiers. | T — test_api.py | passing |
| GD-9 | §8 | Reading a dossier, listing dossiers and every other request except `POST /dossiers` and `POST /dossiers/{domain}/refresh` make no provider call. | T — test_api.py | passing |
| RF-1 | §8 | Starts a new build of the dossier and returns 202 with `{ "dossier_id", "domain", "state": "building" }`. | T — test_builds.py | passing |
| RF-2 | §8 | A refresh received while a build of the dossier is running starts no second build and returns 202 with the same body. | T — test_builds.py, test_idempotency.py | passing |
| RF-3 | §8 | No dossier for the domain \| 404 `not_found` | T — test_api.py | passing |
| RF-4 | §8 | A refresh researches again: its build makes provider calls whether or not anything has changed since the last build, and its spending counts in `spent_units`. | T — test_builds.py | passing |
| RF-5 | §7 | `POST /dossiers/{domain}/refresh` takes no body; any body sent to it is ignored | T — test_idempotency.py | passing |
| LS-1 | §8 | GET /dossiers -> { "dossiers": [ { dossier_id, domain, state, legal_name, researched_at, spent_units } ], "has_more": false } | T — test_api.py | passing |
| LS-2 | §8 | `q` is optional. When present, only dossiers whose domain or `legal_name` contains `q`, compared case-insensitively, are listed. | T — test_api.py | passing |
| LS-3 | §8 | An empty `q` lists every dossier. | T — test_api.py | passing |
| LS-4 | §8 | Dossiers are ordered by domain ascending. | T — test_api.py | passing |
| LS-5 | §8 | `limit` defaults to 50, range 1 to 200. `offset` defaults to 0. `has_more` is true when items exist beyond the last one returned. | T — test_api.py | passing |
| LS-6 | §8 | `legal_name` is the value of the dossier's `legal_name` field, or null. | T — test_api.py | passing |
| LS-7 | §5 | `limit` integer 1 to 200 / `offset` integer 0 or more, otherwise 422 `validation_failed` | T — test_api.py | passing |
| ID-1 | §7 | Header absent or empty \| 400 `missing_idempotency_key` | T — test_idempotency.py | passing |
| ID-2 | §5 | `Idempotency-Key` \| 1 to 255 characters \| 422 `validation_failed` | T — test_idempotency.py | passing |
| ID-3 | §7 | The key is scoped to **the authenticated user**. Two different users may use the same key string with no interaction between them. | T — test_idempotency.py | passing |
| ID-4 | §7 | Replay: same key, same body \| **200**, body identical to the original response as a JSON value | T — test_idempotency.py | passing |
| ID-5 | §7 | Same key, different body \| 409 `idempotency_key_reuse` | T — test_idempotency.py | passing |
| ID-6 | §7 | The same key with the same body on a different path is a different request, not a replay, and must succeed normally. | T — test_idempotency.py | passing |
| ID-7 | §7 | `Acme-Robotics.test` and `acme-robotics.test` in a path or body are different requests for this rule, though they name the same dossier. | T — test_idempotency.py | passing |
| ID-8 | §7 | Key reused after the original request failed with 4xx \| Treated as a first use | T — test_auth.py, test_idempotency.py | passing |
| ID-9 | §7 | "Same body" means the same JSON value after parsing — key order and whitespace do not matter. Unknown fields are ignored (§3.5) and play no part in this comparison | T — test_idempotency.py | passing |
| ID-10 | §7 | any body sent to it is ignored and plays no part in deciding a replay. | T — test_idempotency.py | passing |
| ID-11 | §7 | For concurrent identical requests with an unused key, exactly one returns the normal response. The others return 200 with the same body. The operation takes effect only once. | T — test_idempotency.py | passing |
| ID-12 | §7 | A successful replay returns the original response, even after the dossier has changed. It starts no build and makes no provider call. | T — test_idempotency.py | passing |
| ID-13 | §7 | After the body has parsed as a JSON object and the caller is authenticated, an already claimed key is resolved before field validation. Thus changing a successful request to an invalid body with the same key still returns `409 idempotency_key_reuse`. | T — test_idempotency.py | passing |
| ID-14 | §7 | Everything below applies to each of them independently. | T — test_idempotency.py | passing |
| ID-15 | §7 | [concurrent same key, different bodies] Concurrent requests must produce the same results as executing them one at a time in some order (§11) | T — test_idempotency.py | passing |
| BD-1 | §8 | A dossier has at most one build running at a time. | T — test_builds.py, test_faults.py | passing |
| BD-2 | §8 | A build ends in `ready` when it completed, or `failed` when none of its provider calls succeeded. A failed build leaves the fields as they were. | T — test_faults.py | passing |
| BD-3 | §8 | When a build completes `ready`, each field is `known` exactly when the evidence (§4) supports a value for it. | T — test_builds.py | passing |
| BD-4 | §8 | A build whose provider calls each answer within one second ends within 10 seconds of the request that started it. | T — test_builds.py | passing |
| BD-5 | §8 | Against the live providers [...] a build does not give up on a call that has been waiting less than 30 seconds, nor stop gathering because of the time it has run in its first 120 seconds. It still ends `ready` or `failed` within 300 seconds. | T(proxy)+R — test_faults.py | passing (revision a70e5c6: full run 411 passed); R part (timeouts) open: Reviewer inspection |
| BD-6 | §8 | Reading a dossier, listing dossiers and every other request [...] make no provider call. (idempotent replays, validation failures, health) | T — test_api.py, test_idempotency.py | passing |
| BD-7 | §1 | A dossier is built in the background, read any number of times, and refreshed on request. | T — test_api.py, test_faults.py | passing |
| SU-1 | §1 | Every value the service asserts cites at least one excerpt that a provider endpoint served to this service, and that excerpt supports the value. No citation is invented, reworded, or attached to a value it does not support. | T — test_builds.py | passing |
| SU-2 | §4 | The excerpt is copied character for character from that served text, except that any run of whitespace may be written as a single space. It is 1 to 500 characters long. | T — test_builds.py | passing |
| SU-3 | §4 | It is taken from the page's prose (below), not from its header. | T — test_builds.py | passing |
| SU-4 | §4 | An excerpt **supports** a value when, read on its own, it states that value for that field of this company, as Appendix A defines. | T — test_builds.py | passing |
| SU-5 | §4 | The excerpt may write the value differently from the API: `Acme Robotics has raised $12M.` and `Acme Robotics has raised 12 million dollars.` both support a `funding_total` of `12000000` | T — test_builds.py | passing |
| SU-6 | §4 | When the evidence supports more than one value for a field, the field holds one of them and cites only excerpts that support that value. | T — test_builds.py | passing |
| SU-7 | §4 | A field is `unknown` when no evidence supports a value for it, even when a research answer claims one. | T — test_builds.py | passing |
| SU-8 | §4 | The **evidence** for a company is every page that some search [...] returns, with its full text, and every claim that a `nimble` research run for the company asking for all six fields answers with. [...] The claim is asserted only when its citation supports it. | T — test_builds.py, test_faults.py | passing |
| SU-9 | §4 | `url` is the URL of the page the excerpt was served for, `provider` is `nimble` or `tavily`, the provider that served it. | T — test_builds.py | passing |
| SU-10 | App. A.2/A.3 | It contains none of the negating phrases (A.3). | T — test_builds.py | passing |
| SU-11 | App. A.2 | It names the company: it contains the company's normalised domain, or the company's name. | T — test_builds.py | passing |
| SU-12 | §4 | The header line `Facts:` [...] is informative only: citations come from the prose, and whether an excerpt supports a value is decided by Appendix A alone. | T — test_builds.py | passing |
| SU-13 | §4 | A string value is written as the supporting excerpt writes it, without surrounding whitespace. | T — test_builds.py | passing |
| SU-14 | §4 | A headcount the web states as a number, or as a range that fits inside one of the ranges above, has the range that contains it as its value. | T — test_builds.py | passing |
| SU-15 | §4 | `status` is `known` when `value` is not null, and `unknown` when it is. A `known` field has one or more citations. An `unknown` field has `"value": null` and `"citations": []`. (types: legal_name/hq_city/ceo string; founded_year, funding_total integer; headcount_range one of 8 ranges) | T — test_builds.py | passing |
| A1-1 | App. A.1 | A sentence ends after a `.`, `!` or `?`, together with any `"`, `”`, `’` or `)` directly after it, when whitespace follows. A `.` that ends one of the legal-form suffixes in A.4, written as a whole word, does not end a sentence. An excerpt is a **single sentence** when [...] this rule splits it into exactly one sentence. | T — test_builds.py | passing |
| A2-1 | App. A.2 | An excerpt supports the value V for the field F of a company exactly when all of these hold: 1. single sentence 2. names the company 3. a statement phrase for F 4. none of the negating phrases 5. at least one value in F's format, and every value in F's format that it contains normalises to V. | T — test_builds.py | passing |
| A3-1 | App. A.3 | Statement phrases per field and the list of negating phrases; matched without regard to case and as whole words. | T — test_builds.py | passing |
| A4-L | App. A.4 | `legal_name`: The company's name or its domain, then zero or more capitalised or uppercase words each after one space, then an optional `,`, one space, and a legal-form suffix [...] the shortest counts | T — test_builds.py | passing |
| A4-H | App. A.4 | `hq_city`: A place name directly after a statement phrase for `hq_city` and one space: the longest run of capitalised words joined by single spaces or by `-` | T — test_builds.py | passing |
| A4-C | App. A.4 | `ceo`: A person's name: a run of two or three capitalised words joined by single spaces that is not part of a longer such run. [name and CEO phrases taken out first] | T — test_builds.py | passing |
| A4-F | App. A.4 | `founded_year`: A number of exactly four digits, from 1800 to 2099, that is not part of an amount | T — test_builds.py | passing |
| A4-N | App. A.4 | `headcount_range`: A number with no decimal part, 1 or more, that is not part of an amount. [...] A stated range such as `51-200 employees` holds two numbers | T — test_builds.py | passing |
| A4-M | App. A.4 | `funding_total`: An amount [forms with `$`/`US$`/`USD`, scales k/m/mn/bn/thousand/million/billion; `N dollars`/`US dollars`]. Amounts in other currencies are not amounts. | T — test_builds.py | passing |
| A5-1 | App. A.5 | Normalised value: text as written; year as integer; the §4 range containing the number; funding = number times the scale in US dollars. An amount that does not come to a whole number of dollars is not a value | T — test_builds.py | passing |
| CO-1 | §1/§9 | No build of a dossier spends more than 80 units (§9). | T — test_builds.py, test_faults.py | passing |
| CO-2 | §4 | Of the searches that a provider answers without an error, every build makes exactly one whose query is exactly the company's normalised domain, through a provider of its choice | T — test_builds.py, test_concurrency.py, test_faults.py | passing |
| CO-3 | §4 | its other such searches use other queries. | T — test_builds.py | passing |
| CO-4 | §8/§9 | Each provider call has a cost in units [table]; `spent_units` is the total cost of every provider call made for this dossier | T — test_builds.py, test_concurrency.py, test_faults.py | passing |
| CO-5 | §9 | A call that a provider refuses with an error status costs nothing. | T — test_faults.py | passing |
| CO-6 | §9 | A call whose answer does not arrive, because it times out or its connection fails, costs its units as in the table, whether or not the provider received it. | T(proxy)+R — test_faults.py | passing (test/run); R part open: Reviewer inspection |
| CO-7 | §9 | A research request names the company by its domain in its query, and names the fields it asks for by the field names in §4, as the property names of its output schema. | T — test_builds.py | passing |
| CO-8 | §9 | An extract through `nimble` does not set `render`. | T — test_builds.py | superseded by S2-WEB-1 (RULINGS 46); nimble extract 1 or 3 per URL |
| CO-9 | §9 | A build stops making provider calls before its spending would exceed 80 units, and completes with the pages and research claims it has obtained. | T+R — test_builds.py | passing (test/run); R part open: Reviewer inspection |
| CO-10 | §4 | A search that a provider answers with an error does not count. | T — test_faults.py | passing |
| CO-11 | §9 | Cost table: nimble search 1/5/15, tavily 8/16/16, extract 1/2 per URL, research 25; a search returns at most 10 results (service accounting must match what the mock charges) | T+R — test_builds.py | passing (test/run); R part open: Reviewer inspection |
| CO-12 | §9 | [quality] results per unit: fields known per unit spent (reported by the test run; Reviewer reads it) | M | passing (reported; Reviewer reads) |
| PV-2 | §4 | every claim that a `nimble` research run for the company asking for all six fields answers with (research-only facts are found) | T — test_faults.py | passing |
| PV-3 | §8 | `failed` when none of its provider calls succeeded (all providers erroring -> failed, spent 0) | T — test_faults.py | passing |
| PV-4 | §5 | Requests must not produce 5xx responses [...] when a provider endpoint answers with an error. (search/extract/research errors, 429, throttle) | T — test_faults.py | passing |
| EX-1 | §10 | Return 200 from export with a JSON object containing `track: "dossier"`, `format_version: 1` and `state` (an implementation-defined JSON object). | T — test_state.py | passing |
| EX-2 | §10 | Import takes that entire object and atomically replaces the service's state, returning 204. It must accept an unchanged export produced by this service. | T — test_state.py | passing |
| EX-3 | §10 | Preserve accounts and hashed-password login, existing bearer tokens [...] Existing tokens and retries must remain valid after import | T — test_state.py | passing |
| EX-4 | §10 | Preserve [...] all completed idempotent request bodies and original responses. | T — test_state.py | passing |
| EX-5 | §10 | Import is replacement, not merge; repeating it restores the exported state without duplicating anything. Import removes all previous destination data and credentials. | T — test_state.py | passing |
| EX-6 | §10 | Invalid JSON follows §5; missing fields, wrong track/version or an invalid state give 422 `validation_failed` without changing the destination. | T — test_state.py | passing; ruled (see RULINGS 26-28) |
| EX-7 | §10 | Import makes no provider call: imported dossiers are not researched again, and their citations remain citations served to this service. | T — test_state.py | passing |
| EX-8 | §10 | Export and import do not change the clock. | T — test_state.py | passing |
| EX-9 | §10 | An export taken while a build is running holds the dossier as it was before that build; after import, that dossier is in the state of its last completed build, or `failed` with every field `unknown` when no build had completed. | T — test_state.py | passing |
| EX-10 | §10 | Reset clears all state, including imported state. | T — test_state.py | passing |
| EX-11 | §10 | Export is an atomic, read-only snapshot; subsequent source writes do not change it. | T — test_state.py | passing |
| EX-12 | §10 | No dependency on the source process, files, volume, port or network address is allowed. | T — test_state.py | passing |
| EX-13 | §10 | Failed request keys remain reusable. | T — test_state.py | passing |
| EX-14 | §10 | Like reset, these are unauthenticated control endpoints. [ignore unknown fields; 10-second timeout] | T — test_state.py | passing |
| EX-15 | §10/§3.3 | [a build running in the destination when import replaces its state does not alter the imported state] | T — test_state.py | passing |
| EX-16 | §10 | Identities and timestamps must not be regenerated. | T — test_state.py | passing |
| CC-1 | §2/§11 | Concurrent requests \| up to 50 in flight; no 5xx under concurrent load | T — test_auth.py, test_concurrency.py | passing |
| CC-2 | §11 | Concurrent requests must produce the same results as executing them one at a time in some order. | T — test_auth.py, test_concurrency.py, test_idempotency.py | passing |
| CC-3 | §11 | The requirements above hold at every read. | T — test_builds.py, test_concurrency.py | passing |
| AX-1 | — | [test infrastructure] Appendix A oracle agrees with the spec's own examples and edge cases | T — test_00_oracle.py | passing |
| AX-4 | — | [test infrastructure] citation checker accepts valid and rejects invented/header/wrong-value/hedged citations | T — test_01_checker_selfcheck.py | passing |
| AX-5 | — | [test infrastructure] corpus expectation labels agree with the oracle | T — test_01_checker_selfcheck.py | passing |
| S2-DET-1 | S2 §3 | A field's selected value is the one the selection rule below picks from the field's candidates; the same candidates always yield the same value. | T — test_s2_api.py | passing |
| S2-PG-1 | S2 Page kind | `Kind: own`, `Kind: filing`, `Kind: news`, `Kind: aggregator` \| The page's **kind**: the company's own site, a filing registry, a news report, or an aggregator of company data | T — test_s2_api.py | passing |
| S2-PG-2 | S2 Page kind | A page with no `Kind` line, or with a value not listed above, is of kind `own` when the host of its URL, normalised as `stage-1.md` normalises a domain, is the company's domain, and of kind `aggregator` otherwise. | T — test_s2_api.py | passing |
| S2-PG-3 | S2 Page kind | `Published: <RFC 3339 timestamp>` \| When the page was published (offsets and fractions are instants; two spellings of one instant are equal) | T — test_s2_api.py | passing |
| S2-PG-4 | S2 Page kind | A page with no `Published` line, or with a value that is not an RFC 3339 timestamp, has no publication time. | T — test_s2_api.py | passing |
| S2-PG-5 | S2 Candidates | `kind` is the page's kind, and `published_at` its publication time or null. | T — test_s2_api.py | passing |
| S2-TX-1 | S2 Page text | a page's **text** is the text a browser shows once the page has loaded, without clicking controls. | T — test_s2_api.py | passing |
| S2-TX-2 | S2 Page text | Evidence (§4) is read from page text so defined | T — test_s2_api.py | passing |
| S2-TX-3 | S2 Page text | a citation's excerpt must appear in the page's text. A citation's `provider` is the provider that served the text the excerpt was copied from. | T — test_s2_api.py | passing |
| S2-TX-4 | S2 Page text | Activating disclosure controls is not required. The graded corpus contains no facts that require a click to reveal them. | R | ruled: statement about the graded corpus, not testable; Reviewer notes only |
| S2-WEB-1 | S2 Web access | an extract through `nimble` may ask Nimble to load the page in a browser and serve the text the browser shows once the page has loaded: `provider_options={"render": True}` on WebRouter's extract. (a page whose served text is stale is read through it or a browser vendor) | T — test_s2_api.py | passing |
| S2-WEB-2 | S2 Web access | Cost: extract through `nimble` that loads the page in a browser 3 per URL requested, including a URL for which no page is returned; open a session through `kernel` 0 / `browserbase` 2; each page served to a session 1; browse run 4. A failed open, a failed page load and releasing a session cost nothing. (spent_units = sum of the mock's logged costs) | T — test_s2_api.py | passing |
| S2-WEB-3 | S2 Web access | A service may use Nimble's rendered extract alone to obtain every page's browser text; neither browser vendor is required. | T — test_s2_api.py | passing |
| S2-WEB-4 | S2 Web access | Each provider keeps at most 4 sessions open at once; opening another is answered with an error. A session that no client has been connected to for 60 seconds is closed by the provider. (concurrent builds stay correct) | T+R — test_s2_api.py | passing (test); R part open: Reviewer inspection |
| S2-WEB-5 | S2 Web access | WebRouter reads the keys from the environment. A service that uses these vendors passes their base URLs to WebRouter in `provider_config` (`KERNEL_*`, `BROWSERBASE_*` variables) | R | open: Reviewer inspection |
| S2-CO-1 | S2 Web access/§9 | No build of a dossier spends more than 80 units (§9). (with the render surcharge and browser costs) | T — test_s2_api.py | passing |
| S2-CO-2 | S2 Web access | These calls cost, in the units of §9 [...] (a build's spent_units equals the cost of every provider call the mock logged; exactly one successful domain-query search) | T — test_s2_api.py | passing |
| S2-RL-1 | S2 Rate limits | From this stage a provider may answer any call with 429. (the build still ends `ready` with the right candidates) | T — test_s2_api.py | passing |
| S2-RL-2 | S2 Rate limits | A call answered 429 costs nothing (`stage-1.md` §9). | T — test_s2_api.py | passing |
| S2-RL-3 | S2 Rate limits | No call is answered 429 more than three times in a row [...] (a call that was answered 429 is made again, and succeeds) | T — test_s2_api.py | passing |
| S2-RL-4 | S2 Rate limits | Time a build spends waiting to make a call again after a 429 does not count toward the 10 seconds of `stage-1.md` §8. | T(proxy) — test_s2_api.py | passing (proxy: time bound incl. waits) |
| S2-RL-5 | S2 Rate limits/§5 | [API stays responsive and valid while a build waits on 429s] Requests must not produce 5xx responses | T — test_s2_api.py | passing |
| S2-CA-1 | S2 Candidates | A **candidate** is one value for one field, supported by one excerpt of one page. Every value that a page of the evidence (§4) supports for a field is a candidate of that field, once for each such page. | T — test_s2_api.py | passing |
| S2-CA-2 | S2 Candidates | `url`, `excerpt` and `provider` follow the citation rules in §4. A candidate's `provider` is a provider that served the text its excerpt is taken from. | T — test_s2_api.py | passing |
| S2-CA-3 | S2 Candidates | [a (page, value) pair is a candidate once: two statements of one value on one page are one candidate; one value on several pages is several candidates] | T — test_s2_api.py | passing |
| S2-CA-4 | S2 Candidates | A research claim whose citation does not support it is still not a candidate. | T — test_s2_api.py | passing |
| S2-CA-5 | S2 Candidates | `candidates` lists the candidates of the last build that completed `ready`, in the order the selection rule ranks them, the selected one first. | T — test_s2_api.py | passing |
| S2-CA-6 | S2 Candidates | `retrieved_at` is the time of the build that gathered the candidate (§8, Builds). | T — test_s2_api.py | passing |
| S2-CA-7 | S2 Candidates | A field with no candidate has `"candidates": []` and is `unknown`. | T — test_s2_api.py | passing |
| S2-CA-8 | S2 Candidates/§8 | A failed build leaves the fields as they were (candidates included). | T — test_s2_api.py | passing |
| S2-CA-9 | S2 Candidates | While a later build runs, the candidates are those of the last build that completed `ready`; a completed build replaces them. | T — test_s2_api.py | passing |
| S2-CA-10 | S2 Candidates | The evidence now also holds the page that each research claim of the evidence cites, whether or not the citation supports its claim: a build reads that page as it reads any other. | T — test_s2_api.py | passing |
| S2-SEL-1 | S2 Selection | **Authority** of the page's kind: `own` and `filing` rank equal and highest, then `news`, then `aggregator`. | T — test_s2_api.py | passing |
| S2-SEL-2 | S2 Selection | **Recency** within the same authority: the later `published_at` ranks higher. | T — test_s2_api.py | passing |
| S2-SEL-3 | S2 Selection | A candidate without a publication time ranks below every candidate of the same authority that has one. | T — test_s2_api.py | passing |
| S2-SEL-4 | S2 Selection | **URL**: when authority and publication time are equal, the candidate whose `url` is smaller, comparing the strings by Unicode code point, ranks higher. | T — test_s2_api.py | passing |
| S2-SEL-5 | S2 Selection | **Value**: between two candidates with the same URL and provider, the one whose value is smaller ranks higher: integers compare as numbers, strings by Unicode code point after removing surrounding whitespace. | T — test_s2_api.py | passing |
| S2-SEL-6 | S2 Selection | The highest-ranked candidate is the selected one. The field's `value` is the selected candidate's value, and its `citations` are the `url`, `excerpt` and `provider` of every candidate with that value, in rank order. | T — test_s2_api.py | passing |
| S2-SEL-7 | S2 Candidates | Two values are the same value when they are equal as JSON values; strings are compared exactly, after removing surrounding whitespace. | T — test_s2_api.py | passing |
| S2-SEL-8 | S2 Selection | A candidate of lower authority is selected only when no candidate of higher authority exists for that field. | T — test_s2_api.py | passing |
| S2-SEL-9 | S2 Candidates | `selected` is true on exactly one candidate of a field that has candidates, the one the rule picks, and false on the others. | T — test_s2_api.py | passing |
| S2-SEL-10 | S2 Selection | The rule runs over all of a field's candidates. | T — test_s2_api.py | passing |
| S2-SEL-11 | S2 Selection | between two candidates with the same URL, they rank by provider in the order `nimble`, `tavily`, `kernel`, `browserbase`. (a page is one candidate per value whatever provider served it: not observable black-box; offline model check only) | M | passing (offline model only) |
| S2-ST-1 | S2 Status | `known` \| The field has candidates, and they all have the same value | T — test_s2_api.py | passing |
| S2-ST-2 | S2 Status | `contested` \| The field's candidates carry two or more different values [...] A `contested` field still has a selected `value` and its citations. | T — test_builds.py, test_s2_api.py | passing |
| S2-ST-3 | S2 Status | `unknown` \| The field has no candidate; `value` is null | T — test_s2_api.py | passing |
| S2-LS-1 | S2 Status | `GET /dossiers` (§8) is unchanged. The `legal_name` it lists is the selected value. | T — test_s2_api.py | passing |
| S2-UI-1 | S2 Screens | The following screens must be reachable by URL: `/`, `/dossiers/{domain}`, `/dossiers/{domain}/evidence`, `/contested`, `/signup`, `/login`. Other screens must be reachable through the UI. | T — test_s2_api.py | passing |
| S2-UI-2 | S2 Screens | The browser and the API share `/dossiers/{domain}`. Return the UI for `Accept: text/html`; API requests without that header receive JSON. | T — test_s2_api.py | passing |
| S2-UI-3 | S2 Screens | `/`, `/dossiers/{domain}/evidence` and `/contested` are browser routes; they read the API's dossier data. (screens show what the API holds) | T — test_s2_api.py | passing |
| S2-UI-4 | S2 Screens | The domain in a browser route is normalised as in §4. | T — test_s2_api.py | passing |
| S2-AU-1 | S2 Signup and login | `signup-email`, `signup-password`, `signup-display-name` inputs; `signup-submit` button; `login-email`, `login-password`, `login-submit` (sign up and log in through the UI) | T — test_s2_ui.py | passing |
| S2-AU-2 | S2 Signup and login | `auth-error` \| Error message. Present only when there is one | T — test_s2_ui.py | passing |
| S2-AU-3 | S2 Signup and login | `current-user` \| Visible on every screen when signed in. Text contains the display name | T — test_s2_ui.py | passing |
| S2-AU-4 | S2 Signup and login | `logout-button` \| Button | T — test_s2_ui.py | passing |
| S2-LST-1 | S2 Dossier list | `dossier-list` \| Container. Children ordered by domain ascending | T — test_s2_ui.py | passing |
| S2-LST-2 | S2 Dossier list | `dossier-item-{domain}` \| One per listed dossier. Carries `data-state="{state}"`. Text contains the domain, and the legal name when known. Links to `/dossiers/{domain}` | T — test_s2_ui.py | passing |
| S2-LST-3 | S2 Dossier list | `dossier-search` \| Input. Filters the list as `q` does on `GET /dossiers`; `empty-dossiers` \| Shown instead of the list when no dossier matches | T — test_s2_ui.py | passing |
| S2-LST-4 | S2 Dossier list | A research request that succeeds, with 202 or 200, opens `/dossiers/{domain}` for the normalised domain. `research-domain` input, `research-submit` button sends `POST /dossiers`. | T — test_s2_ui.py | passing |
| S2-LST-5 | S2 Dossier list | `research-error` \| Error message, when the request is refused — including an invalid domain | T — test_s2_ui.py | passing |
| S2-LST-6 | S2 Dossier list | A domain that already has a dossier, including one created by another client after this browser read the list, opens that dossier and starts no build. | T — test_s2_ui.py | passing |
| S2-LST-7 | S2 Dossier list | `research-uncertain` \| Shown when the outcome of a research request is unknown | T — test_s2_ui.py | passing |
| S2-RS-1 | S2 Refresh and competing clients | If a research or refresh response is lost, including after the request commits, show `research-uncertain` or `refresh-uncertain` (nonempty text), not `research-error` or `refresh-error`. | T — test_s2_ui.py | passing |
| S2-RS-2 | S2 Refresh and competing clients | Keep the request retryable with the **same key and body**. | T — test_s2_ui.py | passing |
| S2-RS-3 | S2 Refresh and competing clients | A successful retry removes both the error and the uncertainty elements, shows the dossier, and starts at most one build. Unknown outcomes are not confirmed refusals. | T — test_s2_ui.py | passing |
| S2-DOS-1 | S2 Dossier | `dossier-domain` \| Text is exactly the normalised domain | T — test_s2_ui.py | passing |
| S2-DOS-2 | S2 Dossier | `dossier-state` \| Text is exactly `building`, `ready` or `failed` | T — test_s2_ui.py | passing |
| S2-DOS-3 | S2 Dossier | `dossier-spent` \| Formatted `spent_units`. Carries `data-units="{integer}"` | T — test_s2_ui.py | passing |
| S2-DOS-4 | S2 Dossier | `field-{field}` \| One per field, six in all, in the order of the table in `stage-1.md` §4. Carries `data-status`; `field-value-{field}` \| The formatted value. Carries `data-value`. Present only when the value is not null; `field-contested-{field}` \| A marker. Present only when the field is `contested` | T — test_s2_ui.py | passing |
| S2-DOS-5 | S2 Dossier | `field-citations-{field}` \| Container of the field's citations, in API order; `citation-{field}-{n}` \| The field's `n`th citation, counting from 1. Text contains the excerpt. Contains a link whose `href` is the citation's `url`. Carries `data-provider` | T — test_s2_ui.py | passing |
| S2-DOS-6 | S2 Dossier | `dossier-researched-at` \| Text contains `researched_at`, formatted. Absent when it is null | T — test_s2_ui.py | passing |
| S2-DOS-7 | S2 Dossier | `dossier-evidence-link` \| Link to `/dossiers/{domain}/evidence` | T — test_s2_ui.py | passing |
| S2-DOS-8 | S2 Dossier | `dossier-not-found` \| Shown instead of the fields when no dossier exists for the domain | T — test_s2_ui.py | passing |
| S2-DOS-9 | S2 Dossier | While the dossier's state is `building`, the screen reads the dossier again at least every 2 seconds until the state is `ready` or `failed`, and then shows the new fields without a manual reload. | T — test_s2_ui.py | passing |
| S2-EV-1 | S2 Evidence | `evidence-{field}` \| One container per field, six in all. Children in API `candidates` order | T — test_s2_ui.py | passing |
| S2-EV-2 | S2 Evidence | `candidate-{field}-{n}` \| The field's `n`th candidate, counting from 1. Carries `data-value`, `data-provider`, `data-kind`, `data-url`, `data-published-at` (the RFC 3339 `published_at`, empty when null) and `data-selected="true"` or `"false"` | T — test_s2_ui.py | passing |
| S2-EV-3 | S2 Evidence | `candidate-{field}-{n}` Text contains the formatted value and the excerpt. | T — test_s2_ui.py | passing |
| S2-EV-4 | S2 Evidence | `evidence-empty-{field}` \| Shown instead of candidates when the field has none | T — test_s2_ui.py | passing |
| S2-EV-5 | S2 Screens | `/dossiers/{domain}/evidence`: the domain in the browser route is normalised; an unknown dossier is handled | T — test_s2_ui.py | passing |
| S2-CT-1 | S2 Contested | `contested-item-{domain}-{field}` \| One per contested field of any dossier. Carries `data-value` for the selected value. Text contains the domain, the field and every distinct candidate value. Links to `/dossiers/{domain}/evidence` | T — test_s2_ui.py | passing |
| S2-CT-2 | S2 Contested | `contested-list` \| Container. Children ordered by domain ascending, then by field in the order of the table in `stage-1.md` §4 | T — test_s2_ui.py | passing |
| S2-CT-3 | S2 Contested | `empty-contested` \| Shown instead of the list when no field is contested | T — test_s2_ui.py | passing |
| S2-RF-1 | S2 Dossier/Refresh | `dossier-refresh` \| Button. Sends `POST /dossiers/{domain}/refresh` (with an Idempotency-Key) | T — test_s2_ui.py | passing |
| S2-RF-2 | S2 Dossier | `refresh-error` \| Error message, when a refresh is refused | T — test_s2_ui.py | passing |
| S2-RF-3 | S2 Dossier | `refresh-uncertain` \| Shown when the outcome of a refresh is unknown | T — test_s2_ui.py | passing |
| S2-RF-4 | S2 Refresh and competing clients | [retry of a lost refresh] same key and body | T — test_s2_ui.py | passing |
| S2-RF-5 | S2 Refresh and competing clients | After any successful action, the data on the same page must show the new state without a manual reload. Navigation must wait for the write to succeed before it refreshes the data. | T — test_s2_ui.py | passing |
| S2-RF-6 | S2 Refresh and competing clients | [a lost refresh response, retried: at most one build starts] | T — test_s2_ui.py | passing |
| S2-RF-7 | S2 Refresh and competing clients | A refresh from this browser while that build runs is answered 202 like any other and the screen follows the running build to its end. | T — test_s2_ui.py | passing |
| S2-RW-1 | S2 Refresh and competing clients | `dossier-reload` reads the dossier again. **Latest read wins:** a delayed earlier read must not overwrite a later one, including when responses arrive out of order. | T — test_s2_ui.py | passing |
| S2-RW-2 | S2 Refresh and competing clients | This applies to the reads while a dossier is `building` as well. | T — test_s2_ui.py | passing |
| S2-RW-3 | S2 Dossier | `dossier-reload` \| Button. Reads the dossier again without starting a build | T — test_s2_ui.py | passing |
| S2-UP-1 | S2 Existing clients | A stage-2 service must accept an export produced by the same team's stage-1 service. | T — test_s2_upgrade.py | passing |
| S2-UP-2 | S2 Existing clients | Imported dossiers appear in the list and on their screens. (ids, states, researched_at, spent_units preserved) | T — test_s2_upgrade.py | passing |
| S2-UP-3 | S2 Existing clients | A browser signed in before that export/import upgrade must remain signed in afterwards. (tokens and password logins survive) | T — test_s2_upgrade.py | passing |
| S2-UP-4 | S2 Existing clients | A research or refresh request whose response was lost before export remains retryable after import with the same body and key | T — test_s2_upgrade.py | passing |
| S2-UP-5 | S2 Existing clients | Each imported field gains one candidate for every value that text the providers served to the dossier's last stage-1 build that completed `ready` supports for that field, once for each page whose served text supports it. | T — test_s2_upgrade.py | passing; ruled (RULINGS 55: only what the stage-1 export records) |
| S2-UP-6 | S2 Existing clients | The candidate's excerpt is taken from that text and supports the value; its `provider` is the provider that served that text | T — test_s2_upgrade.py | passing; ruled (RULINGS 55: only what the stage-1 export records) |
| S2-UP-7 | S2 Existing clients | its `kind` and `published_at` are as the exported state records them or else null, and its `retrieved_at` is the dossier's `researched_at`. | T — test_s2_upgrade.py | passing; ruled (RULINGS 55: only what the stage-1 export records) |
| S2-UP-8 | S2 Existing clients | Each imported field's `value`, `status` and `citations` then follow from its candidates by the selection rule and Status, as after a build. | T — test_s2_upgrade.py | passing; ruled (RULINGS 55: only what the stage-1 export records) |
| S2-UP-9 | S2 Existing clients/§10 | [a stage-1 dossier that never completed ready: `failed`, every field `unknown`, no candidates] | T — test_s2_upgrade.py | passing |
| S2-UP-10 | S2 Existing clients | The candidates of an imported dossier are replaced by those of its next completed build. | T — test_s2_upgrade.py | passing |
| S2-UP-11 | S2 Existing clients | A browser signed in before that export/import upgrade must remain signed in afterwards. [...] No page reload or new screen is required. | T — test_s2_ui.py | passing |
| S2-UP-12 | S2 Existing clients | the UI must recover the original response and show the imported dossier. [...] These requirements apply when import completes between browser requests | T — test_s2_ui.py | passing |
| S2-PQ-1 | S2 Product | The required flows must remain clear and usable at a 375 CSS-pixel viewport and at conventional desktop widths, without horizontal page scrolling. | T — test_s2_ui.py | passing |
| S2-PQ-2 | S2 Product | Inputs need visible labels | T — test_s2_ui.py | passing |
| S2-PQ-3 | S2 Product | keyboard focus must be apparent | T(heuristic) — test_s2_ui.py | passing (heuristic test) |
| S2-PQ-4 | S2 Product | text and controls need sufficient contrast | T(heuristic) — test_s2_ui.py | passing (heuristic test) |
| S2-PQ-5 | S2 Product | Known, unknown, contested, building, failed, loading, successful, refused and uncertain states must be visually distinct as well as satisfying the behavioural requirements below. | T+UX — test_s2_ui.py | passing (test, heuristic); UX part open: UX reviewer |
| S2-PQ-6 | S2 Product | keep navigation consistent across the required routes. | T — test_s2_ui.py | passing |
| S2-PQ-7 | S2 Product | Each citation shows its excerpt as quoted text and links to its URL. | T — test_s2_ui.py | passing |
| S2-PQ-8 | S2 Product | Format names, years, headcount ranges, money and timestamps for people first; expose technical identifiers only where they help the user. | T(heuristic)+UX — test_s2_ui.py | passing (test, heuristic); UX part open: UX reviewer |
| S2-PQ-9 | S2 Product | Provide considered empty, loading and error states | T+UX — test_s2_ui.py | passing (test, heuristic); UX part open: UX reviewer |
| S2-PQ-10 | S2 Product | Primary actions — research, refresh — must be easy to identify. | T(heuristic)+UX — test_s2_ui.py | passing (test, heuristic); UX part open: UX reviewer |
| S2-PQ-11 | S2 Product | [no script errors on the required screens] | T — test_s2_ui.py | passing |
| S2-PQ-12 | S2 Product | A field's value and its status must be the clearest information on the dossier screen, with its citations directly beside it. [...] a coherent, presentation-ready research product, [...] a consistent visual system for typography, spacing, colour, controls and feedback. | UX | open: UX reviewer inspection |
| S2-PQ-13 | S2 Product | a reader opening a dossier should see at a glance which fields are known, which are unknown and which are contested, and where each value came from. | UX | open: UX reviewer inspection |
| AX-6 | — | [test infrastructure] selection rule / status / kind / published model agrees with the spec's rules | T — test_02_selection_selfcheck.py | passing |
| AX-7 | — | [test infrastructure] stage-2 corpus expectations are exact (no fragment-only candidates) | T — test_02_selection_selfcheck.py | passing |
