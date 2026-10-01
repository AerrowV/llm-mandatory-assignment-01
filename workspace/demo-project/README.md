# Demo project: textmetrics

A small library the pipeline builds against. It exists so the testing role has
real code to exercise and the two coding workers have genuinely separable work.

## Layout

```
src/textmetrics/__init__.py
src/textmetrics/tokens.py      worker 1 - tokenisation helpers
src/textmetrics/readability.py worker 2 - readability scores
tests/test_tokens.py
tests/test_readability.py
```

Two workers, two modules, no shared files. That is deliberate: it means a
pipeline run can prove real parallelism, because two agents editing the same
file would be a merge conflict rather than a demonstration.

## Status

`tokens.py` and `readability.py` are stubs. Each raises `NotImplementedError`.
The test files exist and currently fail. That is the state the architect and
tech lead roles read, and it is what the coding workers are asked to fix.

## Running the tests

The container has no pytest, so the tests use the standard library:

```bash
cd workspace/demo-project
python3 -m unittest discover -s tests -v
```

`ruff` is not installed either. Static checks use `python3 -m compileall` plus
`python3 -m py_compile`, which is what the testing role reports on. Installing
tools would need approval, so the pipeline does not depend on it.

## TASK.md

The task spec the agents work from.