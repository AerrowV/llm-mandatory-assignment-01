## Checklist
* PASS: configuration is valid
* PASS: security baseline
* PASS: the demo project builds and runs
* FAIL: unit tests pass
  ERROR: test_known_id (test_server.TestGetOne.test_known_id)
  KeyError: 'title'
* FAIL: the server starts and answers /health
  server exited early:
  todo api listening on http://127.0.0.1:8765
  Server started on port 8765
* FAIL: container build and deploy config
  FAIL: litellm reports healthy
    litellm /health/liveliness returned 000
  FAIL: openhands serves the UI
    openhands /canvas returned 000
  FAIL: the proxy serves the role aliases
    ./docker/validate.sh: line 71: LITELLM_URL: unbound variable
    ./docker/validate.sh: line 72: LITELLM_URL: unbound variable
    0 alias(es) served: could not list
    expected at least 7 aliases, got 0