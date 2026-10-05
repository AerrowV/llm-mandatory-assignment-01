
## Setup

Python 3 standard library only, nothing to install.

## Usage

### Operations

- Addition: `python3 run.py add 2 3`
- Subtraction: `python3 run.py subtract 5 2`
- Multiplication: `python3 run.py multiply 4 2`
- Division: `python3 run.py divide 10 2`

### Test Command

To run tests, use: `python3 run.py test`.

## Runbook

- To run the calculator, use: `python3 run.py`.
- Exit codes:
  - 0: Success
  - 1: An operation failed
  - 2: An operation was invalid (e.g., division by zero)

## Troubleshooting

- Error message: `python3 run.py add 2 3` will return an error if the arguments are not integers.
- Wrong exit code: If the calculator returns an exit code other than 0, 1, or 2, it indicates an issue with the operation or the calculator itself.
- Known failures: Refer to the `QUALITY.md` file for known issues and how to resolve them.