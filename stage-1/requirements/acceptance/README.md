# Acceptance tests (stage 1) — black-box, from the specification only

Everything goes through HTTP: the service (`BASE_URL`) and the mock web's admin/log API
(`MOCK_URL`, serving `./corpus`, a corpus written for these tests in the mock's own format;
`gen_corpus.py` regenerates it and checks its labels against `oracle.py`, an independent
implementation of Appendix A).

One command (builds the stage image + mock, runs both on a private docker network, limited to
2 CPU / 3 GiB, starts a second fresh instance for cross-instance import, cleans up):

    ./run.sh                    # all tests;  ./run.sh -k idempotency -x   # any pytest args

Against processes you already run (the service's `NIMBLE_BASE_URL`/`TAVILY_BASE_URL` must point at the mock):

    BASE_URL=http://localhost:8000 MOCK_URL=http://localhost:8080 [BASE_URL_2=http://localhost:8001] ./run_against.sh

Each test names its ledger IDs in its docstring (`../LEDGER.md`); `python3 ledger_audit.py [status.json]`
regenerates the ledger table and lists rows no test covers. `RULINGS.md` lists every reading adopted.
The run ends with a "fields known per unit spent" table for the plausibility read (CO-12).
