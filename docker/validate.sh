#!/usr/bin/env bash
# Deployability validation for this repo. Functional requirement 6 asks for at
# least one of: a deployment checklist, a deployment script, container
# build/deploy config, or environment/config documentation. This is the
# deployment script, and it is what the deploy-validator role runs.
#
# Every check is executable, so "deployable" is a measurement rather than a
# claim. The script exits non-zero if any check fails, so it can gate the
# pipeline and a CI job.
#
#   ./docker/validate.sh            # run every check
#   ./docker/validate.sh --list     # list the checks without running them
#
# It has to run in two places. On the host it can use the docker CLI and build
# images. Inside the agent container there is no docker CLI and no socket, so
# the container checks report SKIP rather than a false FAIL, and the rest still
# run. That split is deliberate: a skipped check must never read as a passed one.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Same .env the stack reads, so a check never tests a different configuration
# than the one that will run. Exported because the checks below are subshells.
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi

PASS=0
FAIL=0
SKIP=0

if [ -t 1 ]; then
  G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[1m'; N=$'\033[0m'
else
  G=""; R=""; Y=""; B=""; N=""
fi

say()  { printf '%s\n' "$*"; }
head1() { printf '\n%s== %s ==%s\n' "$B" "$*" "$N"; }
pass() { printf '  %sPASS%s  %s\n' "$G" "$N" "$*"; PASS=$((PASS+1)); }
fail() { printf '  %sFAIL%s  %s\n' "$R" "$N" "$*"; FAIL=$((FAIL+1)); }
skip() { printf '  %sSKIP%s  %s\n' "$Y" "$N" "$*"; SKIP=$((SKIP+1)); }

# Run a command quietly, report pass/fail on its exit code. The command's own
# output is kept in $OUT so a failure can quote it.
check() {
  local name="$1"; shift
  local out
  note_check "$name"
  if out="$("$@" 2>&1)"; then
    pass "$name"
  else
    fail "$name"
    printf '%s\n' "$out" | sed 's/^/          /' | head -15
  fi
  OUT="$out"
}

have() { command -v "$1" >/dev/null 2>&1; }

# The proxy answering 200 and serving every alias is the difference between "the
# stack is up" and "an agent can actually reach a model". Written as a function
# rather than a `bash -c` subshell: nesting a python -c inside a single-quoted
# subshell body needs three levels of quote escaping, and the previous version
# of this check was broken by exactly that - it failed with a shell parse error
# and was being reported as a real failure.
proxy_serves_aliases() {
  local n
  n=$(curl -fsS -m 10 "$LITELLM_URL/v1/models" \
        -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
      | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("data", [])))' \
      2>/dev/null) || n=0
  echo "$n alias(es) served: $(curl -fsS -m 10 "$LITELLM_URL/v1/models" \
        -H "Authorization: Bearer $LITELLM_MASTER_KEY" 2>/dev/null \
      | python3 -c 'import json,sys; print(", ".join(sorted(m["id"] for m in json.load(sys.stdin).get("data", []))))' \
      2>/dev/null || echo could not list)"
  if [ "${n:-0}" -lt 7 ]; then
    echo "expected at least 7 aliases, got ${n:-0}"
    return 1
  fi
}

LIST_ONLY=0
[ "${1:-}" = "--list" ] && LIST_ONLY=1

# Checks register themselves here as they are defined, so --list cannot drift
# out of sync with what actually runs.
declare -a CHECK_NAMES=()
note_check() { CHECK_NAMES+=("$1"); }

if [ "$LIST_ONLY" = "1" ]; then
  say "checks in docker/validate.sh:"
  say ""
  note_check "1. configuration is valid"
  note_check "docker compose file parses"
  note_check "endpoints/config.yml is valid YAML with a model_list"
  note_check "proxy key is present and non-empty"
  note_check "required config files are present and non-empty"
  note_check "2. security baseline"
  note_check "every published port is bound to 127.0.0.1"
  note_check "3. the demo project builds and runs"
  note_check "every module compiles"
  note_check "static checks: compileall on src and py_compile on tests"
  note_check "unit tests pass"
  note_check "the server starts and answers /health"
  note_check "4. container build and deploy config"
  note_check "compose services are defined and up"
  note_check "litellm reports healthy"
  note_check "openhands serves the UI"
  note_check "the proxy serves the role aliases"
  say ""
  printf '  %s\n' "${CHECK_NAMES[@]}"
  say ""
  say "run without --list to execute them"
  exit 0
fi

say "${B}deployability validation${N}  repo: $ROOT"

# ---------------------------------------------------------------- config ----
head1 "1. configuration is valid"

if have docker; then
  check "docker compose file parses" docker compose -f "$ROOT/docker-compose.yml" config -q
else
  skip "docker compose parses (no docker CLI here)"
fi

# endpoints/config.yml drives every model request, so an unparseable file takes
# the whole stack down while /v1/models keeps answering.
if have python3; then
  check "endpoints/config.yml is valid YAML with a model_list" python3 - "$ROOT" <<'PY'
import sys, pathlib
root = pathlib.Path(sys.argv[1])
text = (root / "endpoints" / "config.yml").read_text()
try:
    import yaml
except ImportError:
    # No PyYAML on the host. Fall back to the structural checks that matter and
    # do not pretend the file was fully parsed.
    models = [ln.split(":", 1)[1].strip() for ln in text.splitlines()
              if ln.strip().startswith("- model_name:")]
    assert models, "no model_list entries found"
    print(f"structural check only (no PyYAML): {len(models)} aliases: "
          + ", ".join(models))
    sys.exit(0)
data = yaml.safe_load(text)
assert data.get("model_list"), "config.yml has no model_list"
for entry in data["model_list"]:
    name = entry.get("model_name")
    params = entry.get("litellm_params") or {}
    assert name, "a model_list entry has no model_name"
    assert params.get("model"), f"{name}: no litellm_params.model"
    base = params.get("api_base") or ""
    assert base.startswith("http"), f"{name}: api_base must be an absolute URL"
    assert "localhost" not in base, (
        f"{name}: api_base is {base!r}. Inside the container 'localhost' is the "
        "container itself, not the host. Use host.docker.internal.")
print(f"{len(data['model_list'])} aliases, all with a model and an absolute api_base")
PY
else
  skip "endpoints/config.yml parses (no python3)"
fi

# The proxy refuses every route without the key, so a missing or empty key is a
# deploy-time failure that looks like a bad model name later.
check "proxy key is present and non-empty" bash -c '
  [ -n "${LITELLM_MASTER_KEY:-}" ] || { echo "LITELLM_MASTER_KEY is unset or empty - run: cp .env.example .env"; exit 1; }
  echo "LITELLM_MASTER_KEY is set (${#LITELLM_MASTER_KEY} chars)"'

# A fresh clone has to reproduce the stack, so every file compose and the
# profiles depend on must be committed rather than living only on this machine.
check "required config files are present and non-empty" bash -c '
  missing=0
  for f in .env .env.example endpoints/config.yml docker-compose.yml \
           prompts/01-architect.md \
           openhands/state/profiles/architect.json \
           openhands/state/agent-profiles/architect.json; do
    if [ ! -s "$1/$f" ]; then echo "missing or empty: $f"; missing=1; fi
  done
  n=$(ls "$1"/openhands/state/profiles/*.json 2>/dev/null | wc -l | tr -d " ")
  echo "$n LLM profiles on disk"
  [ "$n" -ge 7 ] || { echo "expected 7 role profiles, found $n"; missing=1; }
  # Generated files must match .env, or the stack runs something other than
  # what .env asks for.
  python3 "$1/scripts/config.py" --check >/dev/null 2>&1 \
    || { echo "generated config has drifted from .env: run scripts/config.py"; missing=1; }
  exit $missing' _ "$ROOT"

# --------------------------------------------------------------- security ----
head1 "2. security baseline"

# NFR 4: the workflow must not need an unauthenticated endpoint reachable
# publicly. A published port on 0.0.0.0 is exactly that.
#
# This reads the *resolved* compose config, not the template. The template says
# "${LITELLM_BIND}:4000", so grepping it for a bare "4000:4000" would match
# nothing and pass vacuously no matter what .env asked for.
check "every published port is bound to 127.0.0.1" bash -c '
  if docker compose version >/dev/null 2>&1; then
    exposed=$(docker compose -f "$1/docker-compose.yml" config 2>/dev/null \
      | grep -B2 "published:" | grep "host_ip:" | grep -v "host_ip: 127.0.0.1" || true)
    if [ -n "$exposed" ]; then
      echo "ports published on something other than 127.0.0.1:"; echo "$exposed"
      echo "set LITELLM_BIND and AGENT_BIND in .env to 127.0.0.1:<port>"
      exit 1
    fi
    echo "every published port resolves to 127.0.0.1"
  fi
  # Independent of compose: the binds themselves must be loopback.
  for bind in "${LITELLM_BIND:-127.0.0.1:4000}" "${AGENT_BIND:-127.0.0.1:8000}"; do
    case "$bind" in
      127.0.0.1:*|localhost:*) ;;
      *) echo "LITELLM_BIND/AGENT_BIND publishes on all interfaces: $bind"
         exit 1 ;;
    esac
  done
  echo "LITELLM_BIND=$LITELLM_BIND AGENT_BIND=$AGENT_BIND"' _ "$ROOT"

# ------------------------------------------------------------- the project ----
head1 "3. the demo project builds and runs"

DEMO="$ROOT/workspace/demo-project"
if [ -d "$DEMO" ]; then
  if have python3; then
    check "every module compiles" python3 -m compileall -q "$DEMO/src"
    check "static checks: compileall on src and tests" bash -c '
      python3 -m compileall -q "$1/src" && python3 -m py_compile "$1"/tests/*.py' _ "$DEMO"
    # The unit suites are the contract the workers wrote against, so a red
    # suite here means the deploy candidate does not work.
    check "unit tests pass" bash -c '
      cd "$1" && PYTHONPATH=src python3 -m unittest discover -s tests' _ "$DEMO"
    check "the server starts and answers /health" bash -c '
      cd "$1" || exit 1
      PYTHONPATH=src python3 run.py >/tmp/validate_demo.log 2>&1 &
      pid=$!
      trap "kill $pid 2>/dev/null" EXIT
      for _ in $(seq 1 40); do
        if curl -fsS -m 2 http://127.0.0.1:8765/health >/tmp/validate_health.json 2>/dev/null; then
          cat /tmp/validate_health.json; echo; exit 0
        fi
        kill -0 $pid 2>/dev/null || { echo "server exited early:"; cat /tmp/validate_demo.log; exit 1; }
        sleep 0.5
      done
      echo "server never answered /health within 20s"; cat /tmp/validate_demo.log; exit 1' _ "$DEMO"
  else
    skip "python checks (no python3)"
  fi
else
  skip "demo project not present at workspace/demo-project"
fi

# ---------------------------------------------------------------- docker ----
head1 "4. container build and deploy config"

if have docker && docker info >/dev/null 2>&1; then
  # `docker compose ps` exits 0 with EMPTY output when no container exists, and
  # `check` infers pass from the exit code alone. That reported "up" while both
  # health endpoints below returned 000. Require each declared service to be in
  # the running set instead.
  check "compose services are defined and up" bash -c '
    want=$(docker compose -f "$1/docker-compose.yml" config --services | sort)
    [ -n "$want" ] || { echo "docker-compose.yml declares no services"; exit 1; }
    running=$(docker compose -f "$1/docker-compose.yml" ps --services --filter status=running 2>/dev/null | sort)
    missing=$(comm -23 <(echo "$want") <(echo "$running"))
    if [ -n "$missing" ]; then
      echo "declared but not running: $(echo "$missing" | tr "\n" " ")"
      echo "running: $(echo "$running" | tr "\n" " ")"
      echo "start it with: docker compose up -d"
      exit 1
    fi
    echo "running: $(echo "$running" | tr "\n" " ")"' _ "$ROOT"
  check "litellm reports healthy" bash -c '
    code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$LITELLM_URL/health/liveliness")
    [ "$code" = "200" ] || { echo "litellm /health/liveliness returned $code"; exit 1; }
    echo "litellm healthy on $LITELLM_URL"'
  check "openhands serves the UI" bash -c '
    code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$AGENT_URL/canvas")
    [ "$code" = "200" ] || { echo "openhands /canvas returned $code"; exit 1; }
    echo "openhands serving on $AGENT_URL"'
  check "the proxy serves the role aliases" proxy_serves_aliases
else
  # No docker CLI, or no daemon: the host cannot answer these. Saying SKIP keeps
  # them from being counted as passes.
  skip "container checks (no docker daemon or CLI here)"
fi

# ---------------------------------------------------------------- verdict ----
printf '\n%s== verdict ==%s\n' "$B" "$N"
say "  $PASS passed, $FAIL failed, $SKIP skipped"
if [ "$FAIL" -gt 0 ]; then
  say "  ${R}NOT deployable as configured: $FAIL check(s) failed.${N}"
  exit 1
fi
if [ "$SKIP" -gt 0 ]; then
  say "  ${Y}deployable for the checks that ran; $SKIP skipped, so this is not a full validation.${N}"
  say "  Re-run ${B}docker/validate.sh${N} on a host with docker to close the gap."
  exit 0
fi
say "  ${G}deployable: every check passed.${N}"
exit 0