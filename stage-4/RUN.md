# Dossier service — build and run

```sh
docker build -t dossier stage-4
docker run --rm -p 8080:8080 \
  -e PORT=8080 \
  -e NIMBLE_API_KEY=... -e NIMBLE_BASE_URL=https://sdk.nimbleway.com \
  -e TAVILY_API_KEY=unused -e TAVILY_BASE_URL=https://api.tavily.com \
  -e KERNEL_API_KEY=unused -e KERNEL_BASE_URL=https://api.onkernel.com \
  -e BROWSERBASE_API_KEY=unused -e BROWSERBASE_BASE_URL=https://api.browserbase.com \
  dossier
curl http://localhost:8080/health      # {"status": "ok"}
```

State (accounts, dossiers, batches, the change feed, idempotent responses and the clock) is written to a journal under `DATA_DIR` (default `/var/lib/dossier`, in the container's
filesystem) before every request that changes it is answered, so it survives `docker stop`, `docker kill`
and `docker start` of the same container. Give `-v dossier-data:/var/lib/dossier` to keep it beyond the container.

Open `http://localhost:8080/` in a browser for the UI: dossier list and research form (`/`), one
dossier (`/dossiers/{domain}`), its evidence (`/dossiers/{domain}/evidence`), contested fields
(`/contested`), `/signup` and `/login`. `/dossiers/{domain}` answers the UI for `Accept: text/html` and
JSON otherwise. The UI is plain HTML, CSS and JavaScript from `dossier_service/static/`: no build
step, no external fonts or scripts.

`NIMBLE_BASE_URL` must be the real endpoint, a mock endpoint, or unset — never empty.
With `NIMBLE_BASE_URL` unset or on `sdk.nimbleway.com` the service waits as long as the live
provider needs (45 s per search or extract, 150 s per research run, 285 s per build); against any
other host it uses short timeouts. Tavily, Kernel and Browserbase are not used: every call goes to Nimble.

Domains are normalised once (spec §4): `POST /dossiers {"domain": "www.www.acme.test"}` creates the
dossier `www.acme.test`, which `GET /dossiers/www.acme.test` cannot address, because that path
normalises to `acme.test`.

## Design in brief

* One Python process (`dossier_service/`), standard-library HTTP server, state in memory behind a
  lock and in an append-only journal on disk. Every provider call goes through `web_router` in-process.
* `support.py` implements Appendix A. `evidence.py` reads a page's browser text and turns every
  sentence that supports a value into a candidate (one per page and value) with the page's kind
  and publication time. `selection.py` ranks a field's candidates (authority, recency, URL,
  provider, value), selects the first, and derives `value`, `status` and `citations`.
* `builder.py` spends the 80 units where they buy most: one `lite` search on the bare domain and one
  per field (1 unit each) name pages, one research run (25 units) names the pages its claims cite,
  and what is left reads pages through Nimble's rendered extract (3 units a page, cited pages
  first, then the likeliest). A page whose URL, title and snippet never name the company is first
  checked with a plain extract (1 unit) and rendered only if the text it serves names the company. Page text is read only from the rendered extract, because a search or
  a plain extract can serve text a browser does not show. `gateway.py` retries a 429 after 1.05 s
  (up to three times); that waiting does not count toward the build's time window.
* `dossier.py` is one dossier: its builds (each with the pages it gathered and the eight fields it left),
  the history of every field and the rule for what counts as a `change` or a `correction`. A finished
  build is applied in one step under the store lock, so each change is recorded, and numbered in the
  feed, exactly once. `versions.py` holds the page-version rules behind `GET /dossiers/{domain}/values`
  (`true_from` from `Effective`, else the UTC date of `Published`).
* `lineage.py` reads a page's `Registrant`, `Canonical` and `First-Published-By` lines and derives its origin
  (first publisher, else the original's origin through at most three `Canonical` hops, else the company for a
  lookalike, else the registrant). `evidence.py` classifies kinds (a page is `own` only when its registrant is the
  company) and settles origins when a build ends; `builder.py` looks up each original a copy's origin needs
  with one plain extract (1 unit), keeping some budget back from the first round of page reads for that.
  `corroboration.py` derives `corroborated_since` from the builds' views, so it is recomputed, not stored.
* `investors` (`support.py` `investor_names`, `selection.py` `investors_of`) is a field whose value is the sorted
  names that an own or filing page, or two origins, state; history and feed entries for it follow `dossier.py`.
* `POST /batches` and `GET /batches/{id}` (`batches.py`, `store.py`): one batch is a budget shared by the first
  builds of the domains that have no dossier yet. Every call a build makes reserves its cost with `ledger.py`
  against the build's own 80 units and the batch's budget, and the store journals the reservation (a
  light `progress` record, flushed but not forced to disk) before the call is made.
  After a restart, a build found running is over: it ends `failed` (fields as they were) with every
  reserved unit counted, in flight or not, for its dossier and its batch.
* Provider errors (5xx, 429) cost nothing and are retried (`gateway.py`); a build ends `failed` only when no
  call was answered.
* `store.py` holds users, tokens, dossiers, the change feed, idempotency records and the export/import
  format; reset and import bump an epoch so a build still running cannot change what follows.
  `codec.py` turns dossiers into their exported form and back. A stage-3 export (no `investors`, no origins: a
  candidate's origin is the host of its URL) is upgraded there, and its builds keep their pages. A stage-1 or
  stage-2 export is upgraded there too: it counts as one ready build at `researched_at` (stage 1: each cited excerpt becomes a candidate
  for every field it supports; stage 2: its candidates are kept, and `true_from` follows from their
  publication time, since the export holds no `Effective` line), and its fields get one `initial` history entry.
* `persistence.py` is the journal: one JSON line per batch of changed records, flushed with `fsync` before
  the request that made the change is answered, compacted to one atomic snapshot at start. A torn last
  line from an abrupt stop is ignored. The clock reading is part of it.
* `ui.py` and `static/` serve the browser UI, which reads the JSON API with the bearer token kept in
  `localStorage`. A research or refresh whose response is lost stays retryable with the same key.

## Tests

```sh
pip install -r requirements.txt -c constraints.txt
python -m unittest discover -s tests
```
