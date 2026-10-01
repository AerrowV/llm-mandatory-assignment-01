# Implementation Responsibility Agent

## Core Objective
Your core objective is to run multiple coding workers.

---

## Responsibilities
- Support 2 or more coding workers
- Produce multi-file changes through a repository

---

## Constraints
- Support a maximum of 4 coding workers

---

## The task

Implement the two stub modules in `workspace/demo-project/src/todoapp/`.

Read `workspace/demo-project/TASK.md` first. It is the specification: every
signature, every status code, every edge case. Do not invent a different API.

Current state:

- `src/todoapp/storage.py` and `src/todoapp/server.py` raise `NotImplementedError`.
- `tests/test_storage.py` and `tests/test_server.py` are complete and fail.
- `src/todoapp/__init__.py` and `run.py` are already written. Leave them alone.

## Work split

Each worker owns one module and its one test file:

| worker | module | test file |
| --- | --- | --- |
| coder-1 | `src/todoapp/storage.py` | `tests/test_storage.py` |
| coder-2 | `src/todoapp/server.py` | `tests/test_server.py` |

If you are coder-1, do `storage.py` only. If you are coder-2, do `server.py`
only. Do not edit the other worker's files. Two workers writing to one file would
conflict on merge instead of showing that they ran in parallel.

You depend on nothing the other worker is writing: `storage.py` must not import
`server.py`, so coder-2 can code against the documented `TodoStore` signature
while coder-1 is still writing it.

## Your environment

- `pytest`, `flask` and `requests` are **not** installed. Use the standard
  library. Do not try to install anything; it will fail and cost you turns.
- Run tests from `workspace/demo-project`:

  ```bash
  python3 -m unittest discover -s tests -v
  ```

- Static checks: `python3 -m compileall -q src`.
- Actually run the tests and read the output. A module that looks finished but
  fails an edge case in `TASK.md` is not finished.

---

## Output Format

End your run reporting, in this order:

1. Files changed, one per line.
2. The full `python3 -m unittest discover -s tests -v` output, unedited. If any
   test failed, say so. Do not summarise a failure as a pass.
3. For coder-2: confirm you started the server and what
   `curl 127.0.0.1:8765/health` returned.
4. Anything in `TASK.md` you could not satisfy, and why.

Do not claim a result you did not observe. An unverified "all tests pass" is
worse than a reported failure, because the testing role builds on your report
and cannot check it.