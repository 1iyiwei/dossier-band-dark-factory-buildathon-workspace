# Dossier service — build and run

```sh
docker build -t dossier stage-2
docker run --rm -p 8080:8080 \
  -e PORT=8080 \
  -e NIMBLE_API_KEY=... -e NIMBLE_BASE_URL=https://sdk.nimbleway.com \
  -e TAVILY_API_KEY=unused -e TAVILY_BASE_URL=https://api.tavily.com \
  -e KERNEL_API_KEY=unused -e KERNEL_BASE_URL=https://api.onkernel.com \
  -e BROWSERBASE_API_KEY=unused -e BROWSERBASE_BASE_URL=https://api.browserbase.com \
  dossier
curl http://localhost:8080/health      # {"status": "ok"}
```

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

* One Python process (`dossier_service/`), standard-library HTTP server, in-memory state behind a
  lock. Every provider call goes through `web_router` in-process.
* `support.py` implements Appendix A. `evidence.py` reads a page's browser text and turns every
  sentence that supports a value into a candidate (one per page and value) with the page's kind
  and publication time. `selection.py` ranks a field's candidates (authority, recency, URL,
  provider, value), selects the first, and derives `value`, `status` and `citations`.
* `builder.py` spends the 80 units where they buy most: one `lite` search on the bare domain and one
  per field (1 unit each) name pages, one research run (25 units) names the pages its claims cite,
  and what is left reads pages through Nimble's rendered extract (3 units a page, cited pages
  first, then the likeliest). Page text is read only from the rendered extract, because a search or
  a plain extract can serve text a browser does not show. `gateway.py` retries a 429 after 1.05 s
  (up to three times); that waiting does not count toward the build's time window.
* `store.py` holds users, tokens, dossiers, idempotency records and the export/import format; reset
  and import bump an epoch so a build still running cannot change what follows. A stage-1 export
  imports: each cited excerpt of a field becomes a candidate with no kind or publication time,
  retrieved at the dossier's `researched_at`, and the field is recomputed by the selection rule.
* `ui.py` and `static/` serve the browser UI, which reads the JSON API with the bearer token kept in
  `localStorage`. A research or refresh whose response is lost stays retryable with the same key.

## Tests

```sh
pip install -r requirements.txt -c constraints.txt
python -m unittest discover -s tests
```
