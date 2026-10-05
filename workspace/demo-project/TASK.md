# Task spec for the coding workers

Implement the two stub modules in `src/calc/`. Each worker owns exactly one
file. Do not edit the other worker's file, `run.py`, the tests or this file.
Standard library only.

## Module 1 — `src/calc/ops.py` (coder-1)

Four functions. Each takes two numbers and returns a number.

```python
def add(a: float, b: float) -> float: ...
def subtract(a: float, b: float) -> float: ...
def multiply(a: float, b: float) -> float: ...
def divide(a: float, b: float) -> float: ...
```

- `divide(a, 0)` raises `ValueError("cannot divide by zero")`.
- `ops.py` must not import anything from `cli.py`.

## Module 2 — `src/calc/cli.py` (coder-2)

One function. Import the four operations with
`from calc.ops import add, subtract, multiply, divide`.

```python
def main(argv: list[str]) -> int: ...
```

`argv` is the operation and two numbers, for example `["add", "2", "3"]`.

- Print the result and return `0`. Print a whole number without a decimal
  point (`5`, not `5.0`); otherwise print it as is (`2.5`).
- Wrong number of arguments, an unknown operation, or a value that is not a
  number: print a message starting with `error:` and return `2`.
- Division by zero: print a message starting with `error:` and return `1`.

## Done when

```bash
python3 -m unittest discover -s tests     # all tests pass
python3 run.py add 2 3                     # prints 5
```
