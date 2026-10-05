## Setup

Python 3 standard library only, no additional installation required.

## Usage

Each of the four operations can be run using the following command:

```bash
python3 run.py <operation>
```

Where `<operation>` can be one of the following:

- `add`: Add two numbers
- `subtract`: Subtract the second number from the first
- `multiply`: Multiply the two numbers
- `divide`: Divide the first number by the second

Here are examples of each operation:

```bash
# Add two numbers
python3 run.py add 5 3

# Subtract the second number from the first
python3 run.py subtract 5 3

# Multiply the two numbers
python3 run.py multiply 5 3

# Divide the first number by the second
python3 run.py divide 5 3
```

## Runbook

To run the calculator, simply execute the following command:

```bash
python3 run.py
```

The calculator will exit with the following exit codes:

- `0`: The operation was successful
- `1`: An error occurred during the operation
- `2`: An error occurred during the operation and the operation was not performed

## Troubleshooting

If you encounter an error, please check the output for any error messages. If you receive an unexpected exit code, please refer to the runbook for the meanings of the exit codes.

Known failures from the tests are as follows:

- The calculator does not handle division by zero.
- The calculator does not handle non-numeric inputs.

If you have any questions or need further assistance, please contact the support team.