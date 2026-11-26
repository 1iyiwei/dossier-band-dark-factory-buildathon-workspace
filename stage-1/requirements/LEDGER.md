# LEDGER (stage 1)

Kinds: T acceptance test (`requirements/acceptance`), RUN run.sh measurement, R review inspection, M measurement. Status: open / passing / failing / ruled.

| ID | § | Requirement (quoted) | Verification | Status |
|---|---|---|---|---|
| DEP-1 | §2 | Deliver an HTTP service, a `Dockerfile` and a `RUN.md` with a command that builds and starts the service without manual setup. | RUN+R | open |
| DEP-2 | §3.1 | Listen on `0.0.0.0` using the `PORT` environment variable, default `8080`. | RUN | open |
| DEP-3 | §3.2 | Return 200 once the service and its data store can serve requests, within 60 seconds of container start. | RUN | open |
| DEP-4 | §2 | CPU \| 2 vCPU; Memory \| 3 GiB; Concurrent requests \| up to 50 in flight (run.sh limits the container to 2 CPU / 3 GiB and runs the load tests) | RUN | open |
| DEP-5 | §2 | The image must run on its own with `-e PORT=<port>` and a port mapping. All runtime dependencies, initialization and seed data must work within that single container. | RUN+R | open |
| DEP-6 | §2 | The stage folder's dependency manifest lists `webrouter>=0.12.0`. | R | open |
| DEP-7 | §2 | every request to a provider goes through `web_router`: called in-process, or from a Python helper process that the service runs inside its own container. [...] Calling a provider's API by any other route is not permitted. | R | open |
| DEP-8 | §2 | Tavily is optional: a service may use it beside Nimble, and its absence must not prevent research while Nimble answers. | T — test_faults.py | open |
| DEP-9 | §2 | at run time, **only the provider endpoints this specification lists** [...] Runtime assets and dependencies must be included in the image. | R | open |
| H-1 | §3.2 | GET /health -> 200 {"status": "ok"} | T — test_auth.py | open |
| H-2 | §3.2 | `/health` makes no provider call. | T — test_api.py | open |
| R-1 | §3.3 | When reset returns 204, subsequent requests must see only that fixture: no users other than the seeded ones, no dossiers and no stored idempotent responses. | T — test_auth.py, test_faults.py | open |
| R-2 | §3.3 | Repeated resets are supported. | T — test_auth.py | open |
| R-3 | §3.3 | A build still running when reset is called must not change the state that follows the reset. | T — test_faults.py, test_state.py | open |
| R-4 | §3.3 | This control endpoint must be enabled in the delivered image and requires no authentication. | T — test_auth.py | open |
| R-5 | §4 | A fixture with two users sharing an email is a reset error: 422 `validation_failed`, changing nothing. | T — test_auth.py | open |
| R-6 | §4 | `now` is required and sets the clock (§3.4). | T — test_auth.py | open |
| R-7 | §4/§6 | Seeded users must be able to log in with the given password immediately. / For a user seeded by the fixture (§3.3), `user_id` is that user's `id` in the fixture. | T — test_auth.py | open |
| CK-1 | §3.4 | Reset sets the clock to the fixture's `now`. | T — test_state.py | open |
| CK-2 | §3.4 | The clock stands still between calls: two requests with no clock call between them read the same time. | T — test_state.py | open |
| CK-3 | §3.4 | A `now` earlier than the clock's current time is 422 `validation_failed` and changes nothing. | T — test_auth.py, test_state.py | open |
| CK-4 | §3.4 | `POST /_test/clock` requires no authentication. (-> 204 No Content) | T — test_auth.py | open |
| CK-5 | §3.4 | `now` is an RFC 3339 timestamp with an explicit offset. | T — test_auth.py | open |
| CK-6 | §5 | Reserve 400 `malformed_request` for a body that does not parse or a field of the wrong type. (applied to the clock body) | T — test_auth.py | open |
| CK-7 | §3.4 | Every timestamp the service records or returns is read from this clock. | T — test_builds.py, test_state.py | open |
| CK-8 | §3.4 | Before the first reset the clock follows the system time. | T — test_00_fresh_clock.py | open |
| CV-1 | §3.5 | Requests and responses are `application/json; charset=utf-8`. | T — test_auth.py | open |
| CV-2 | §3.5 | Unknown fields in a request body are ignored, never an error. | T — test_api.py, test_auth.py | open |
| CV-3 | §3.5 | Unknown query parameters are ignored. | T — test_api.py | open |
| CV-4 | §3.5 | IDs are opaque strings of at most 64 characters. | T — test_api.py, test_auth.py | open |
| CV-5 | §3.5 | Timestamps in responses are RFC 3339 with an explicit offset | T — test_api.py | open |
| CV-6 | §5 | Every 4xx and 5xx response carries this body: { "error": { "code": "not_found", "message": "..." } } | T — test_auth.py | open |
| CV-7 | §5 | 400 `malformed_request`: Unparseable body, or a field of the wrong JSON type | T — test_auth.py | open |
| CV-8 | §5 | An integer-valued **query parameter** is written as plain decimal digits: `1e9`, `4.0` and `+4` are 422 `validation_failed` whatever their numeric value. | T — test_api.py | open |
| CV-9 | §5 | `Idempotency-Key` 1 to 255 characters; `limit` integer 1 to 200; `offset` integer 0 or more; otherwise 422 `validation_failed` | T — test_api.py | open |
| CV-10 | §5 | Requests must not produce 5xx responses, including under concurrent load and when a provider endpoint answers with an error. | T — test_concurrency.py | open |
| CV-11 | §2 | Per-request timeout \| 5 s (10 s for `POST /_test/reset`) | T — test_concurrency.py | open |
| AU-1 | §6 | POST /auth/signup -> 201 { "user_id": "u_1", "display_name": "Ada", "token": "..." } | T — test_auth.py | open |
| AU-2 | §6 | POST /auth/login -> 200 { "user_id", "display_name", "token" } | T — test_auth.py | open |
| AU-3 | §6 | Email already registered \| 409 `email_taken` | T — test_auth.py | open |
| AU-4 | §6 | Password shorter than 8 characters \| 422 `validation_failed` | T — test_auth.py | open |
| AU-5 | §6 | `email` not of the form `local@domain` \| 422 `validation_failed` | T — test_auth.py | open |
| AU-6 | §6 | `display_name` empty or longer than 100 characters \| 422 `validation_failed` | T — test_auth.py | open |
| AU-7 | §6 | Wrong password or unknown email on login \| 401 `unauthenticated` | T — test_auth.py | open |
| AU-8 | §6 | Every other endpoint requires a bearer token, except `/health`, the `/_test/*` endpoints and the two above. | T — test_auth.py | open |
| AU-9 | §6 | A request to such an endpoint that lacks a valid token is 401 `unauthenticated`, even when it also lacks a required `Idempotency-Key`. | T — test_auth.py | open |
| AU-10 | §6 | Tokens do not expire. An account may have multiple valid tokens and concurrent sessions. | T — test_auth.py | open |
| AU-11 | §6 | Passwords must be stored using a password-hashing function such as bcrypt, scrypt or Argon2, or an equivalent. Plaintext password storage is not permitted. | T+R — test_state.py | open |
| AU-12 | §5 | 401 `unauthenticated`: Missing, malformed or unknown bearer token | T — test_auth.py | open |
| AU-13 | §6/§5 | A required field or query parameter is missing [...] 422; a field of the wrong JSON type 400 (signup/login bodies) | T — test_auth.py | open |
| AU-14 | §6/§11 | Email already registered \| 409 `email_taken` (under concurrent signups: results as one-at-a-time) | T — test_auth.py | open |
| DM-1 | §4 | Every domain the API takes, in a body or a path, is first **normalised**: surrounding whitespace removed, lowercased, one trailing `.` removed, and one leading `www.` removed. | T — test_api.py | open |
| DM-2 | §4 | The normalised domain must then be a valid host name: two or more labels separated by `.`, each label 1 to 63 characters of `a-z`, `0-9` and `-`, not starting or ending with `-`, and 253 characters or fewer in total. Anything else, including a URL with a scheme or a path, is 422 `validation_failed`. | T — test_api.py | open |
| DM-3 | §4 | `Acme-Robotics.TEST.`, `www.acme-robotics.test` and `acme-robotics.test` name the same company and the same dossier. | T — test_api.py | open |
| DM-4 | §4 | Responses always carry the normalised domain. | T — test_api.py | open |
| DM-5 | §4/§8 | The domain in the path is normalised (§4). [invalid -> 422] | T — test_api.py | open |
| PD-1 | §8 | 202 { "dossier_id": "d_7", "domain": "acme-robotics.test", "state": "building" } (new dossier: creates it and starts its first build) | T — test_api.py | open |
| PD-2 | §8 | When a dossier already exists for the domain, the service starts no build and returns **200** with that dossier's `dossier_id`, `domain` and current `state`. | T — test_api.py | open |
| PD-3 | §8 | `domain` missing \| 422 `validation_failed`; `domain` invalid after normalisation \| 422 `validation_failed` | T — test_api.py | open |
| PD-4 | §5 | 400 `malformed_request` for a field of the wrong JSON type (`domain` not a string) | T — test_api.py | open |
| PD-6 | §8 | Concurrent requests for the same domain create one dossier and start one build, whatever their keys. | T — test_concurrency.py, test_idempotency.py | open |
| PD-7 | §8 | [POST /dossiers for an existing domain] starts no build (no provider call) | T — test_api.py | open |
| GD-1 | §8 | `fields` always holds all six fields. [with value/status/citations shape; types per §4 table] | T — test_api.py | open |
| GD-2 | §8 | `state` is `building` while a build runs, otherwise the outcome of the latest build, `ready` or `failed`. | T — test_api.py | open |
| GD-3 | §8 | Before the first build completes `ready`, every field is `unknown`. | T — test_api.py | open |
| GD-4 | §8 | While a later build runs, `fields` are those of the last build that completed `ready`. | T — test_builds.py, test_concurrency.py, test_faults.py | open |
| GD-5 | §8 | `researched_at` is the time of the last build that completed `ready`, or null. / A build's **time** is the clock's time when the request that started it was received. | T — test_builds.py, test_faults.py, test_state.py | open |
| GD-6 | §8 | `spent_units` is the total cost (§9) of every provider call made for this dossier, by every build, since it was created. | T — test_builds.py | open |
| GD-7 | §8 | The domain in the path is normalised (§4). No dossier for it is 404 `not_found`. | T — test_api.py | open |
| GD-8 | §4 | Every authenticated user sees the same dossiers. | T — test_api.py | open |
| GD-9 | §8 | Reading a dossier, listing dossiers and every other request except `POST /dossiers` and `POST /dossiers/{domain}/refresh` make no provider call. | T — test_api.py | open |
| RF-1 | §8 | Starts a new build of the dossier and returns 202 with `{ "dossier_id", "domain", "state": "building" }`. | T — test_builds.py | open |
| RF-2 | §8 | A refresh received while a build of the dossier is running starts no second build and returns 202 with the same body. | T — test_builds.py, test_idempotency.py | open |
| RF-3 | §8 | No dossier for the domain \| 404 `not_found` | T — test_api.py | open |
| RF-4 | §8 | A refresh researches again: its build makes provider calls whether or not anything has changed since the last build, and its spending counts in `spent_units`. | T — test_builds.py | open |
| RF-5 | §7 | `POST /dossiers/{domain}/refresh` takes no body; any body sent to it is ignored | T — test_idempotency.py | open |
| LS-1 | §8 | GET /dossiers -> { "dossiers": [ { dossier_id, domain, state, legal_name, researched_at, spent_units } ], "has_more": false } | T — test_api.py | open |
| LS-2 | §8 | `q` is optional. When present, only dossiers whose domain or `legal_name` contains `q`, compared case-insensitively, are listed. | T — test_api.py | open |
| LS-3 | §8 | An empty `q` lists every dossier. | T — test_api.py | open |
| LS-4 | §8 | Dossiers are ordered by domain ascending. | T — test_api.py | open |
| LS-5 | §8 | `limit` defaults to 50, range 1 to 200. `offset` defaults to 0. `has_more` is true when items exist beyond the last one returned. | T — test_api.py | open |
| LS-6 | §8 | `legal_name` is the value of the dossier's `legal_name` field, or null. | T — test_api.py | open |
| LS-7 | §5 | `limit` integer 1 to 200 / `offset` integer 0 or more, otherwise 422 `validation_failed` | T — test_api.py | open |
| ID-1 | §7 | Header absent or empty \| 400 `missing_idempotency_key` | T — test_idempotency.py | open |
| ID-2 | §5 | `Idempotency-Key` \| 1 to 255 characters \| 422 `validation_failed` | T — test_idempotency.py | open |
| ID-3 | §7 | The key is scoped to **the authenticated user**. Two different users may use the same key string with no interaction between them. | T — test_idempotency.py | open |
| ID-4 | §7 | Replay: same key, same body \| **200**, body identical to the original response as a JSON value | T — test_idempotency.py | open |
| ID-5 | §7 | Same key, different body \| 409 `idempotency_key_reuse` | T — test_idempotency.py | open |
| ID-6 | §7 | The same key with the same body on a different path is a different request, not a replay, and must succeed normally. | T — test_idempotency.py | open |
| ID-7 | §7 | `Acme-Robotics.test` and `acme-robotics.test` in a path or body are different requests for this rule, though they name the same dossier. | T — test_idempotency.py | open |
| ID-8 | §7 | Key reused after the original request failed with 4xx \| Treated as a first use | T — test_auth.py, test_idempotency.py | open |
| ID-9 | §7 | "Same body" means the same JSON value after parsing — key order and whitespace do not matter. Unknown fields are ignored (§3.5) and play no part in this comparison | T — test_idempotency.py | open |
| ID-10 | §7 | any body sent to it is ignored and plays no part in deciding a replay. | T — test_idempotency.py | open |
| ID-11 | §7 | For concurrent identical requests with an unused key, exactly one returns the normal response. The others return 200 with the same body. The operation takes effect only once. | T — test_idempotency.py | open |
| ID-12 | §7 | A successful replay returns the original response, even after the dossier has changed. It starts no build and makes no provider call. | T — test_idempotency.py | open |
| ID-13 | §7 | After the body has parsed as a JSON object and the caller is authenticated, an already claimed key is resolved before field validation. Thus changing a successful request to an invalid body with the same key still returns `409 idempotency_key_reuse`. | T — test_idempotency.py | open |
| ID-14 | §7 | Everything below applies to each of them independently. | T — test_idempotency.py | open |
| ID-15 | §7 | [concurrent same key, different bodies] Concurrent requests must produce the same results as executing them one at a time in some order (§11) | T — test_idempotency.py | open |
| BD-1 | §8 | A dossier has at most one build running at a time. | T — test_builds.py, test_faults.py | open |
| BD-2 | §8 | A build ends in `ready` when it completed, or `failed` when none of its provider calls succeeded. A failed build leaves the fields as they were. | T — test_faults.py | open |
| BD-3 | §8 | When a build completes `ready`, each field is `known` exactly when the evidence (§4) supports a value for it. | T — test_builds.py | open |
| BD-4 | §8 | A build whose provider calls each answer within one second ends within 10 seconds of the request that started it. | T — test_builds.py | open |
| BD-5 | §8 | Against the live providers [...] a build does not give up on a call that has been waiting less than 30 seconds, nor stop gathering because of the time it has run in its first 120 seconds. It still ends `ready` or `failed` within 300 seconds. | T(proxy)+R — test_faults.py | open |
| BD-6 | §8 | Reading a dossier, listing dossiers and every other request [...] make no provider call. (idempotent replays, validation failures, health) | T — test_api.py, test_idempotency.py | open |
| BD-7 | §1 | A dossier is built in the background, read any number of times, and refreshed on request. | T — test_api.py, test_faults.py | open |
| SU-1 | §1 | Every value the service asserts cites at least one excerpt that a provider endpoint served to this service, and that excerpt supports the value. No citation is invented, reworded, or attached to a value it does not support. | T — test_builds.py | open |
| SU-2 | §4 | The excerpt is copied character for character from that served text, except that any run of whitespace may be written as a single space. It is 1 to 500 characters long. | T — test_builds.py | open |
| SU-3 | §4 | It is taken from the page's prose (below), not from its header. | T — test_builds.py | open |
| SU-4 | §4 | An excerpt **supports** a value when, read on its own, it states that value for that field of this company, as Appendix A defines. | T — test_builds.py | open |
| SU-5 | §4 | The excerpt may write the value differently from the API: `Acme Robotics has raised $12M.` and `Acme Robotics has raised 12 million dollars.` both support a `funding_total` of `12000000` | T — test_builds.py | open |
| SU-6 | §4 | When the evidence supports more than one value for a field, the field holds one of them and cites only excerpts that support that value. | T — test_builds.py | open |
| SU-7 | §4 | A field is `unknown` when no evidence supports a value for it, even when a research answer claims one. | T — test_builds.py | open |
| SU-8 | §4 | The **evidence** for a company is every page that some search [...] returns, with its full text, and every claim that a `nimble` research run for the company asking for all six fields answers with. [...] The claim is asserted only when its citation supports it. | T — test_builds.py, test_faults.py | open |
| SU-9 | §4 | `url` is the URL of the page the excerpt was served for, `provider` is `nimble` or `tavily`, the provider that served it. | T — test_builds.py | open |
| SU-10 | App. A.2/A.3 | It contains none of the negating phrases (A.3). | T — test_builds.py | open |
| SU-11 | App. A.2 | It names the company: it contains the company's normalised domain, or the company's name. | T — test_builds.py | open |
| SU-12 | §4 | The header line `Facts:` [...] is informative only: citations come from the prose, and whether an excerpt supports a value is decided by Appendix A alone. | T — test_builds.py | open |
| SU-13 | §4 | A string value is written as the supporting excerpt writes it, without surrounding whitespace. | T — test_builds.py | open |
| SU-14 | §4 | A headcount the web states as a number, or as a range that fits inside one of the ranges above, has the range that contains it as its value. | T — test_builds.py | open |
| SU-15 | §4 | `status` is `known` when `value` is not null, and `unknown` when it is. A `known` field has one or more citations. An `unknown` field has `"value": null` and `"citations": []`. (types: legal_name/hq_city/ceo string; founded_year, funding_total integer; headcount_range one of 8 ranges) | T — test_builds.py | open |
| A1-1 | App. A.1 | A sentence ends after a `.`, `!` or `?`, together with any `"`, `”`, `’` or `)` directly after it, when whitespace follows. A `.` that ends one of the legal-form suffixes in A.4, written as a whole word, does not end a sentence. An excerpt is a **single sentence** when [...] this rule splits it into exactly one sentence. | T — test_builds.py | open |
| A2-1 | App. A.2 | An excerpt supports the value V for the field F of a company exactly when all of these hold: 1. single sentence 2. names the company 3. a statement phrase for F 4. none of the negating phrases 5. at least one value in F's format, and every value in F's format that it contains normalises to V. | T — test_builds.py | open |
| A3-1 | App. A.3 | Statement phrases per field and the list of negating phrases; matched without regard to case and as whole words. | T — test_builds.py | open |
| A4-L | App. A.4 | `legal_name`: The company's name or its domain, then zero or more capitalised or uppercase words each after one space, then an optional `,`, one space, and a legal-form suffix [...] the shortest counts | T — test_builds.py | open |
| A4-H | App. A.4 | `hq_city`: A place name directly after a statement phrase for `hq_city` and one space: the longest run of capitalised words joined by single spaces or by `-` | T — test_builds.py | open |
| A4-C | App. A.4 | `ceo`: A person's name: a run of two or three capitalised words joined by single spaces that is not part of a longer such run. [name and CEO phrases taken out first] | T — test_builds.py | open |
| A4-F | App. A.4 | `founded_year`: A number of exactly four digits, from 1800 to 2099, that is not part of an amount | T — test_builds.py | open |
| A4-N | App. A.4 | `headcount_range`: A number with no decimal part, 1 or more, that is not part of an amount. [...] A stated range such as `51-200 employees` holds two numbers | T — test_builds.py | open |
| A4-M | App. A.4 | `funding_total`: An amount [forms with `$`/`US$`/`USD`, scales k/m/mn/bn/thousand/million/billion; `N dollars`/`US dollars`]. Amounts in other currencies are not amounts. | T — test_builds.py | open |
| A5-1 | App. A.5 | Normalised value: text as written; year as integer; the §4 range containing the number; funding = number times the scale in US dollars. An amount that does not come to a whole number of dollars is not a value | T — test_builds.py | open |
| CO-1 | §1/§9 | No build of a dossier spends more than 80 units (§9). | T — test_builds.py, test_faults.py | open |
| CO-2 | §4 | Of the searches that a provider answers without an error, every build makes exactly one whose query is exactly the company's normalised domain, through a provider of its choice | T — test_builds.py, test_concurrency.py, test_faults.py | open |
| CO-3 | §4 | its other such searches use other queries. | T — test_builds.py | open |
| CO-4 | §8/§9 | Each provider call has a cost in units [table]; `spent_units` is the total cost of every provider call made for this dossier | T — test_builds.py, test_concurrency.py, test_faults.py | open |
| CO-5 | §9 | A call that a provider refuses with an error status costs nothing. | T — test_faults.py | open |
| CO-6 | §9 | A call whose answer does not arrive, because it times out or its connection fails, costs its units as in the table, whether or not the provider received it. | T(proxy)+R — test_faults.py | open |
| CO-7 | §9 | A research request names the company by its domain in its query, and names the fields it asks for by the field names in §4, as the property names of its output schema. | T — test_builds.py | open |
| CO-8 | §9 | An extract through `nimble` does not set `render`. | T — test_builds.py | open |
| CO-9 | §9 | A build stops making provider calls before its spending would exceed 80 units, and completes with the pages and research claims it has obtained. | T+R — test_builds.py | open |
| CO-10 | §4 | A search that a provider answers with an error does not count. | T — test_faults.py | open |
| CO-11 | §9 | Cost table: nimble search 1/5/15, tavily 8/16/16, extract 1/2 per URL, research 25; a search returns at most 10 results (service accounting must match what the mock charges) | T+R — test_builds.py | open |
| CO-12 | §9 | [quality] results per unit: fields known per unit spent (reported by the test run; Reviewer reads it) | M | open |
| PV-2 | §4 | every claim that a `nimble` research run for the company asking for all six fields answers with (research-only facts are found) | T — test_faults.py | open |
| PV-3 | §8 | `failed` when none of its provider calls succeeded (all providers erroring -> failed, spent 0) | T — test_faults.py | open |
| PV-4 | §5 | Requests must not produce 5xx responses [...] when a provider endpoint answers with an error. (search/extract/research errors, 429, throttle) | T — test_faults.py | open |
| EX-1 | §10 | Return 200 from export with a JSON object containing `track: "dossier"`, `format_version: 1` and `state` (an implementation-defined JSON object). | T — test_state.py | open |
| EX-2 | §10 | Import takes that entire object and atomically replaces the service's state, returning 204. It must accept an unchanged export produced by this service. | T — test_state.py | open |
| EX-3 | §10 | Preserve accounts and hashed-password login, existing bearer tokens [...] Existing tokens and retries must remain valid after import | T — test_state.py | open |
| EX-4 | §10 | Preserve [...] all completed idempotent request bodies and original responses. | T — test_state.py | open |
| EX-5 | §10 | Import is replacement, not merge; repeating it restores the exported state without duplicating anything. Import removes all previous destination data and credentials. | T — test_state.py | open |
| EX-6 | §10 | Invalid JSON follows §5; missing fields, wrong track/version or an invalid state give 422 `validation_failed` without changing the destination. | T — test_state.py | open |
| EX-7 | §10 | Import makes no provider call: imported dossiers are not researched again, and their citations remain citations served to this service. | T — test_state.py | open |
| EX-8 | §10 | Export and import do not change the clock. | T — test_state.py | open |
| EX-9 | §10 | An export taken while a build is running holds the dossier as it was before that build; after import, that dossier is in the state of its last completed build, or `failed` with every field `unknown` when no build had completed. | T — test_state.py | open |
| EX-10 | §10 | Reset clears all state, including imported state. | T — test_state.py | open |
| EX-11 | §10 | Export is an atomic, read-only snapshot; subsequent source writes do not change it. | T — test_state.py | open |
| EX-12 | §10 | No dependency on the source process, files, volume, port or network address is allowed. | T — test_state.py | open |
| EX-13 | §10 | Failed request keys remain reusable. | T — test_state.py | open |
| EX-14 | §10 | Like reset, these are unauthenticated control endpoints. [ignore unknown fields; 10-second timeout] | T — test_state.py | open |
| EX-15 | §10/§3.3 | [a build running in the destination when import replaces its state does not alter the imported state] | T — test_state.py | open |
| EX-16 | §10 | Identities and timestamps must not be regenerated. | T — test_state.py | open |
| CC-1 | §2/§11 | Concurrent requests \| up to 50 in flight; no 5xx under concurrent load | T — test_auth.py, test_concurrency.py | open |
| CC-2 | §11 | Concurrent requests must produce the same results as executing them one at a time in some order. | T — test_auth.py, test_concurrency.py, test_idempotency.py | open |
| CC-3 | §11 | The requirements above hold at every read. | T — test_builds.py, test_concurrency.py | open |
| AX-1 | — | [test infrastructure] Appendix A oracle agrees with the spec's own examples and edge cases | T — test_00_oracle.py | open |
| AX-4 | — | [test infrastructure] citation checker accepts valid and rejects invented/header/wrong-value/hedged citations | T — test_01_checker_selfcheck.py | open |
| AX-5 | — | [test infrastructure] corpus expectation labels agree with the oracle | T — test_01_checker_selfcheck.py | open |
