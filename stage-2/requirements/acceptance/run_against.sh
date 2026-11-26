#!/usr/bin/env bash
# Run the acceptance tests against already-running processes.
#   BASE_URL=http://localhost:8000 MOCK_URL=http://localhost:8080 ./run_against.sh [pytest args]
# BASE_URL: the service. MOCK_URL: mock web serving ./corpus with MOCK_ADMIN_TOKEN (default
# local-admin); the service's NIMBLE_BASE_URL/TAVILY_BASE_URL must point at that mock.
# BASE_URL_2 (optional): a second fresh instance, enables the cross-instance import test.
# BASE_URL_S1 (optional): the team's stage-1 service, wired to the same mock: stage-1 -> stage-2 upgrade tests.
# The UI tests need Playwright + Chromium: PYTHON (default: the kickoff package's .venv if it has
# playwright, else ./.venv with requirements.txt and `playwright install chromium`).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
: "${BASE_URL:?set BASE_URL}"
: "${MOCK_URL:?set MOCK_URL}"
PY="${PYTHON:-}"
KICK="${KICKOFF_DIR:-/Users/lwei/Trees/band-dark-factory-buildathoan-workspace/sf-buildathon-2026}"
if [ -z "$PY" ] && [ -x "$KICK/.venv/bin/python" ] && "$KICK/.venv/bin/python" -c "import pytest, httpx, playwright" 2>/dev/null; then
  PY="$KICK/.venv/bin/python"
fi
if [ -z "$PY" ]; then
  if [ ! -x "$HERE/.venv/bin/python" ] || ! "$HERE/.venv/bin/python" -c "import playwright" 2>/dev/null; then
    python3 -m venv "$HERE/.venv"
    "$HERE/.venv/bin/pip" install -q -r "$HERE/requirements.txt"
    "$HERE/.venv/bin/python" -m playwright install chromium
  fi
  PY="$HERE/.venv/bin/python"
fi
cd "$HERE"
exec "$PY" -m pytest -p no:cacheprovider -q -ra "$@"
