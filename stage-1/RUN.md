# Dossier service — build and run

```sh
docker build -t dossier stage-1
docker run --rm -p 8080:8080 \
  -e PORT=8080 \
  -e NIMBLE_API_KEY=... -e NIMBLE_BASE_URL=https://sdk.nimbleway.com \
  -e TAVILY_API_KEY=unused -e TAVILY_BASE_URL=https://api.tavily.com \
  dossier
curl http://localhost:8080/health      # {"status": "ok"}
```

`NIMBLE_BASE_URL` must be the real endpoint, a mock endpoint, or unset — never empty.
With `NIMBLE_BASE_URL` unset or on `sdk.nimbleway.com` the service waits as long as the live
provider needs (45 s per search or extract, 150 s per research run, 285 s per build); against any
other host it uses short timeouts. Tavily is not used: every call goes to Nimble.

## Design in brief

* One Python process (`dossier_service/`), standard-library HTTP server, in-memory state behind a
  lock. Every provider call goes through `web_router` in-process.
* `support.py` implements Appendix A. A value is asserted only with citations that
  `supported_value` accepts; excerpts are whole sentences copied from the prose of a served text.
* `builder.py` spends units where they buy most: the one required search on the bare domain
  (`fast`, 5 units), one `lite` search (1 unit) per field still short of authoritative support,
  an extract (1 unit) only for pages whose snippet was cut short, and a research run (25 units)
  only while some field has no support at all. A build never passes 80 units (`ledger.py`).
* `store.py` holds users, tokens, dossiers, idempotency records and the export/import format;
  reset and import bump an epoch so a build still running cannot change what follows.

## Tests

```sh
pip install -r requirements.txt -c constraints.txt
python -m unittest discover -s tests
```
