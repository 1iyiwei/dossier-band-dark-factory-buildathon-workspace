#!/usr/bin/env bash
# One command: build the stage image and the mock web, start both on a private docker
# network (service limited to 2 CPU / 3 GiB), run every acceptance test, clean up.
#   ./run.sh [pytest args]          (STAGE_DIR defaults to ../.., KICKOFF_DIR is the read-only kickoff package)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
STAGE_DIR="${STAGE_DIR:-$(cd "$HERE/../.." && pwd)}"
KICKOFF_DIR="${KICKOFF_DIR:-/Users/lwei/Trees/band-dark-factory-buildathoan-workspace/sf-buildathon-2026}"
S1_DIR="${S1_DIR:-$STAGE_DIR/../stage-1}"      # the team's final stage-1 service (upgrade tests); S1_DIR="" skips them
S2_DIR="${S2_DIR:-$STAGE_DIR/../stage-2}"      # the team's final stage-2 service (upgrade tests); S2_DIR="" skips them
TAG="an$$"
NET="net-$TAG"; MOCKC="mock-$TAG"; SVC="svc-$TAG"; SVC2="svc2-$TAG"; SVC3="svc3-$TAG"; SVCS1="svcs1-$TAG"; SVCS2="svcs2-$TAG"
cleanup() { docker rm -f "$MOCKC" "$SVC" "$SVC2" "$SVC3" "$SVCS1" "$SVCS2" >/dev/null 2>&1; docker network rm "$NET" >/dev/null 2>&1; }
trap cleanup EXIT
set -e
docker build -q -t "dossier-web-$TAG" "$KICKOFF_DIR/challenges/dossier/web" >/dev/null
docker build -q -t "dossier-svc-$TAG" "$STAGE_DIR" >/dev/null
docker network create "$NET" >/dev/null
docker run -d --name "$MOCKC" --network "$NET" --network-alias web -e MOCK_ADMIN_TOKEN=local-admin \
  -v "$HERE/corpus:/data/corpus:ro" -p 127.0.0.1::8080 "dossier-web-$TAG" >/dev/null
MOCK_PORT=$(docker port "$MOCKC" 8080/tcp | head -1 | sed 's/.*://')
for i in $(seq 1 60); do curl -fs "http://127.0.0.1:$MOCK_PORT/_mock/health" >/dev/null && break; sleep 1; done
start_svc() {  # name, extra docker args
  local name="$1"; shift
  docker run -d --name "$name" --network "$NET" --cpus 2 --memory 3g \
    -e NIMBLE_API_KEY=local -e NIMBLE_BASE_URL=http://web:8080/nimble \
    -e TAVILY_API_KEY=local -e TAVILY_BASE_URL=http://web:8080/tavily \
    -e KERNEL_API_KEY=local -e KERNEL_BASE_URL=http://web:8080/kernel \
    -e BROWSERBASE_API_KEY=local -e BROWSERBASE_BASE_URL=http://web:8080/browserbase "$@" >/dev/null
}
wait_health() {  # port -> prints seconds to first healthy answer (DEP-3: <= 60)
  local t0=$(date +%s)
  for i in $(seq 1 120); do
    if curl -fs "http://127.0.0.1:$1/health" | grep -q '"ok"'; then echo $(( $(date +%s) - t0 )); return 0; fi
    sleep 0.5
  done
  echo "never healthy" >&2; return 1
}
# DEP-2: default port 8080 when PORT is unset
start_svc "$SVC3" -p 127.0.0.1::8080 "dossier-svc-$TAG"
P3=$(docker port "$SVC3" 8080/tcp | head -1 | sed 's/.*://')
echo "DEP-2/DEP-3: healthy on default port 8080 after $(wait_health "$P3")s"
docker rm -f "$SVC3" >/dev/null
# the service under test has a fixed host port: RESTART_CMD kills it (SIGKILL) and starts the same container again
P1=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
start_svc "$SVC" -e PORT=8000 -p 127.0.0.1:$P1:8000 "dossier-svc-$TAG"
start_svc "$SVC2" -e PORT=8000 -p 127.0.0.1::8000 "dossier-svc-$TAG"
P2=$(docker port "$SVC2" 8000/tcp | head -1 | sed 's/.*://')
echo "DEP-3: healthy with -e PORT=8000 after $(wait_health "$P1")s"; wait_health "$P2" >/dev/null
BASE_S1=""
if [ -n "$S1_DIR" ] && [ -f "$S1_DIR/Dockerfile" ]; then
  docker build -q -t "dossier-svc1-$TAG" "$S1_DIR" >/dev/null
  start_svc "$SVCS1" -e PORT=8000 -p 127.0.0.1::8000 "dossier-svc1-$TAG"
  PS1=$(docker port "$SVCS1" 8000/tcp | head -1 | sed 's/.*://')
  wait_health "$PS1" >/dev/null && BASE_S1="http://127.0.0.1:$PS1"
fi
BASE_S2=""
if [ -n "$S2_DIR" ] && [ -f "$S2_DIR/Dockerfile" ]; then
  docker build -q -t "dossier-svc2-$TAG" "$S2_DIR" >/dev/null
  start_svc "$SVCS2" -e PORT=8000 -p 127.0.0.1::8000 "dossier-svc2-$TAG"
  PS2=$(docker port "$SVCS2" 8000/tcp | head -1 | sed 's/.*://')
  wait_health "$PS2" >/dev/null && BASE_S2="http://127.0.0.1:$PS2"
fi
RESTART="docker kill $SVC >/dev/null && docker start $SVC >/dev/null"
set +e
RESTART_CMD="$RESTART" BASE_URL_S2="$BASE_S2" BASE_URL="http://127.0.0.1:$P1" BASE_URL_2="http://127.0.0.1:$P2" BASE_URL_S1="$BASE_S1" MOCK_URL="http://127.0.0.1:$MOCK_PORT" \
  "$HERE/run_against.sh" "$@"
RC=$?
echo "DEP-4 resource peek: $(docker stats --no-stream --format '{{.Name}} mem={{.MemUsage}} cpu={{.CPUPerc}}' "$SVC")"
docker logs "$SVC" 2>&1 | tail -n 30 > "$HERE/last-service-log.txt"
exit $RC
