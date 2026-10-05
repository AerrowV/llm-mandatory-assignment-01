#!/usr/bin/env bash
# Deployment validation: config, security baseline, demo project, running stack.
# Prints PASS/FAIL per check and exits 1 if any check failed.

cd "$(dirname "$0")/.." || exit 1
DEMO=workspace/demo-project
PASS=0
FAIL=0

check() {
  local name=$1; shift
  if out=$("$@" 2>&1); then
    echo "  PASS  $name"; PASS=$((PASS + 1))
  else
    echo "  FAIL  $name"; echo "$out" | tail -5 | sed 's/^/          /'; FAIL=$((FAIL + 1))
  fi
}

echo "== 1. configuration"
check "docker compose file parses" docker compose config -q
check ".env has a proxy key" grep -q '^LITELLM_MASTER_KEY=.' .env
check "generated config lists all 7 roles" \
  test "$(grep -c 'model_name:' endpoints/config.yml)" -eq 7

echo "== 2. security baseline"
check "every published port is bound to 127.0.0.1" \
  bash -c '! docker compose config | grep "host_ip:" | grep -v "127.0.0.1"'

echo "== 3. demo project"
check "modules compile" python3 -m compileall -q $DEMO/src
check "unit tests pass" bash -c "cd $DEMO && python3 -m unittest discover -s tests"
check "the CLI runs: run.py add 2 3 prints 5" \
  bash -c "cd $DEMO && test \"\$(python3 run.py add 2 3)\" = 5"

echo "== 4. running stack"
check "litellm is healthy" curl -fs http://localhost:4000/health/liveliness
check "openhands answers" curl -fs -o /dev/null http://localhost:8000/canvas

echo "== verdict"
echo "  $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "  deployable" || { echo "  NOT deployable"; exit 1; }
