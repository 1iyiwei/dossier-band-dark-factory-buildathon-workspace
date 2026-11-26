# Acceptance tests (stage 2) — black-box, from the specifications only

Everything goes through the service's external interfaces: HTTP (`BASE_URL`), the mock web's
admin/log API (`MOCK_URL`, serving `./corpus`, written for these tests in the mock's own format;
`gen_corpus.py` regenerates it and checks its labels against `oracle.py`, an independent
implementation of stage-1 Appendix A, and against `s2model.py`, an independent implementation of the
stage-2 selection rule) and, for the screens, a real Chromium driven by Playwright
(`data-testid` only).

One command (builds the stage image, the team's final stage-1 image and the mock, runs them on a
private docker network limited to 2 CPU / 3 GiB, starts a second fresh instance for cross-instance import,
cleans up):

    ./run.sh                     # all tests;  ./run.sh -k "s2_ui and refresh" -x   # any pytest args
    ./run.sh --ignore=test_s2_ui.py                                                 # API only

Against processes you already run:

    BASE_URL=http://localhost:8000 MOCK_URL=http://localhost:8080 \
      [BASE_URL_2=http://localhost:8001] [BASE_URL_S1=http://localhost:8002] ./run_against.sh

* the service's `NIMBLE_BASE_URL`/`TAVILY_BASE_URL` (and `KERNEL_*`, `BROWSERBASE_*`) must point at the mock;
* `BASE_URL_2`: a second fresh instance (cross-instance import test);
* `BASE_URL_S1`: the team's **stage-1** service (`../../stage-1`) wired to the same mock: enables the
  stage-1 → stage-2 export/import upgrade tests (`test_s2_upgrade.py`; skipped when unset, always set by `run.sh`);
* Python with `pytest`, `httpx`, `playwright` and Chromium: `run_against.sh` uses the kickoff package's
  `.venv` when it has them, else creates `./.venv` and runs `playwright install chromium` (or set `PYTHON`);
  `HEADED=1` shows the browser.

## Files

| File | What |
|---|---|
| `test_00_*`, `test_01_*` | stage-1 model/oracle self-checks (no service) |
| `test_02_selection_selfcheck.py` | stage-2 model self-checks: selection rule, status, kind, `Published` (no service) |
| `test_api.py` … `test_state.py` | stage-1 tests, carried forward and adapted to stage 2 (three statuses, `candidates`, exact candidate sets, render cost) |
| `test_s2_api.py` | candidates, selection rule, status, kind/published, browser text, web access cost, 429, route sharing |
| `test_s2_upgrade.py` | stage-1 export → stage-2 import |
| `test_s2_ui.py` | the six screens, polling, latest-read-wins, uncertain outcomes, upgrade in the browser, product-quality heuristics |
| `s2model.py` | stage-2 selection/status/kind/candidate-expectation model |
| `gen_corpus.py`, `corpus/`, `expectations.json` | the mock corpus and stage-1 labels; stage-2 companies are exact (see below) |
| `ledger_data.py`, `ledger_audit.py`, `status.json` | source of `../LEDGER.md` (`python3 ledger_audit.py status.json`) |

Stage-2 companies (gen_corpus.py): `ashgrove-labs.test` (each step of the selection rule),
`brightmoor-energy.test` (browser text ≠ served text; research-cited unsearchable pages; an unsupported claim),
`cobalt-harbor.test` (page kind / `Published` defaults), `driftwood-games.test` (same value on several pages,
URL code-point ties, duplicates, unknown fields). `gen_corpus.py` asserts the designed outcomes against the model.

Each test names its ledger IDs in its docstring (`../LEDGER.md`); `RULINGS.md` lists every reading adopted.
The run ends with a "fields known per unit spent" table for the plausibility read (CO-12).
