
## Setup

Python 3 standard library only, no external installations required.

## Usage

### Operations

- Addition: `python3 run.py add 2 3`
- Subtraction: `python3 run.py subtract 5 2`
- Multiplication: `python3 run.py multiply 4 2`
- Division: `python3 run.py divide 10 2`

### Test Command

To run tests: `python3 run.py test`

## Runbook

- To run the calculator: `python3 run.py`
- Exit codes:
  - 0: Success
  - 1: Invalid operation
  - 2: Division by zero

## Troubleshooting

- Error message: `python3 run.py add 2 0` will result in an error as division by zero is not allowed.
- Wrong exit code: If the calculator exits with code 1, it means the operation is invalid.
- Known failures: From the `QUALITY.md` file, the calculator fails when dividing by zero and when the operation is invalid.