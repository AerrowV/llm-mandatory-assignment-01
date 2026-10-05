### Test results

- `test_cli.py`: 3 failures, 1 error

### Static checks

- `src/calc/ops.py`: SyntaxError: invalid syntax

### Known limitations and risks

- The implementation does not handle division by zero gracefully.
- The tests do not cover error handling for invalid inputs.
- The CLI does not validate user inputs for division by zero.