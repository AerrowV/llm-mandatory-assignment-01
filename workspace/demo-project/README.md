## Setup

Python 3 standard library only, no additional installation required.

## Usage

### Addition

```bash
python3 run.py add 2 3
```

### Subtraction

```bash
python3 run.py subtract 5 2
```

### Multiplication

```bash
python3 run.py multiply 4 2
```

### Division

```bash
python3 run.py divide 10 2
```

## Runbook

- **How to run**: Use `python3 run.py` followed by the operation and operands.
- **Exit codes**:
  - 0: Operation successful.
  - 1: Division by zero.
  - 2: Invalid operation or operands.

## Troubleshooting

- **Error:** The calculator will raise a `ValueError` when dividing by zero.
- **Wrong exit code:** The calculator will return an exit code of 1 if the division by zero occurs.
- **Known failures:** From the `QUALITY.md` file, the calculator fails when the operands are not integers or floats, and when the operation is not one of the four basic arithmetic operations.