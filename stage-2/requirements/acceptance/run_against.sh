#!/usr/bin/env bash
# Run the acceptance tests against already-running processes.
#   BASE_URL=http://localhost:8000 MOCK_URL=http://localhost:8080 ./run_against.sh [pytest args]
# BASE_URL: the service. MOCK_URL: mock web serving ./corpus with MOCK_ADMIN_TOKEN (default
# local-admin); the service's NIMBLE_BASE_URL/TAVILY_BASE_URL must point at that mock.
# BASE_URL_2 (optional): a second fresh instance, enables the cross-instance import test.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
: "${BASE_URL:?set BASE_URL}"
: "${MOCK_URL:?set MOCK_URL}"
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if [ ! -x "$HERE/.venv/bin/python" ]; then
    python3 -m venv "$HERE/.venv"
    "$HERE/.venv/bin/pip" install -q -r "$HERE/requirements.txt"
  fi
  PY="$HERE/.venv/bin/python"
fi
cd "$HERE"
exec "$PY" -m pytest -p no:cacheprovider -q -ra "$@"
