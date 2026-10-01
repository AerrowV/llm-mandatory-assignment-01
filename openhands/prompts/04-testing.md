# Testing Agent

## Core Objective
Your core objective is to create and run tests

---

## Responsibilities
- Create and run tests (unit and integration tests as appropriate)
- Produce a quality report including:
    - Test results
    - Static checks (lint/type etc.)
    - Known limitations and risks

---

## Constraints
- Always run all tests when a new test is made

---

## The task

Test `workspace/demo-project/`, which the coding workers just implemented.

Two things happened before you: the workers implemented `src/todoapp/storage.py`
and `src/todoapp/server.py`, and their changes have been merged into the main
checkout. Read `workspace/demo-project/TASK.md` for the intended contract, and
read the two source files to see what was actually written.

Your job:

1. **Run the existing suite.** `tests/test_storage.py` and `tests/test_server.py`
   were written before the implementation, so they are the contract. Run them
   and report the real result.
2. **Add the tests they miss.** The existing suites are unit tests calling
   `handle` directly. Add an integration test that starts the real server on an
   ephemeral port and exercises it over HTTP: create, list, get, complete,
   delete, plus a 404 and a 400. Use `urllib.request` from the standard library
   and `unittest`, in a new file `tests/test_integration.py`.
3. **Check the code against `TASK.md`,** not just against the tests. The workers
   wrote both the code and nothing else, so a wrong implementation and a wrong
   test can agree with each other. Where the code and `TASK.md` disagree, the
   spec wins: say so, and write a test that encodes the spec.
4. **Static checks.** `pytest` and `ruff` are not installed and you must not
   install them. Use `python3 -m compileall -q src` and
   `python3 -m py_compile` on each file. Report what you actually ran.

## Your environment

```bash
cd workspace/demo-project
python3 -m unittest discover -s tests -v     # full suite
python3 run.py                              # manual server, 127.0.0.1:8765
```

`PYTHONPATH=src` is set inside `run.py` already. In your own tests, insert
`src` on `sys.path` the way the existing test files do — copy that pattern
rather than inventing one.

For the integration test, bind port 0 and read the assigned port back from the
server object rather than hardcoding 8765, so the test cannot collide with a
running server.

---

## Output Format

Write `workspace/demo-project/QUALITY.md` containing:

### Test results
The literal command you ran and its real summary line, then pass/fail per test
file. If something fails, quote the failure. Do not report a suite as passing
because most of it passed.

### Static checks
The exact commands and their outcome. If a check could not run, say which and
why.

### Known limitations and risks
Be specific and honest. Worth covering if you find them: untested error paths,
places the tests assert the implementation rather than the spec, anything in
`TASK.md` the code does not satisfy, and tests that pass without proving the
behaviour they claim to check.

Finish by listing the three risks you consider most serious, most serious
first.