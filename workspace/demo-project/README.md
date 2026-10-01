# Demo project: todoapp

A small HTTP API the pipeline builds against. It exists so the coding workers
have a real task and the testing role has real behaviour to exercise.

Standard library only. No Flask, no pytest, no pip installs: the agent container
has none of them and installing needs approval.

## Layout

```
src/todoapp/__init__.py
src/todoapp/storage.py   worker 1 - the in-memory store, no HTTP involved
src/todoapp/server.py    worker 2 - HTTP routing on top of the store
tests/test_storage.py    worker 1
tests/test_server.py     worker 2
run.py                   entry point, already written
```

Two workers, two modules, no shared file. That split is deliberate. Two agents
editing the same file would produce a merge conflict, not a demonstration that
parallel workers work.

## Status

`storage.py` and `server.py` are stubs. Every function raises
`NotImplementedError`. The test files are complete and currently fail.

## Running it

```bash
cd workspace/demo-project
PYTHONPATH=src python3 run.py            # listens on 127.0.0.1:8765
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Static checks are `python3 -m compileall -q src`. `ruff` is not installed.

`TASK.md` is the specification the agents work from.