def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(f"error: wrong number of arguments: {len(argv)}")
        return 2
    op, a, b = argv
    try:
        a = float(a)
        b = float(b)
    except ValueError:
        print(f"error: {a} or {b} is not a number")
        return 2
    if op == "add":
        return int(a + b)
    elif op == "subtract":
        return int(a - b)
    elif op == "multiply":
        return int(a * b)
    elif op == "divide":
        if b == 0:
            print("error: cannot divide by zero")
            return 1
        return int(a / b)
    else:
        print(f"error: unknown operation: {op}")
        return 2