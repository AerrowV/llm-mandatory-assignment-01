def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"error: wrong number of arguments: {len(argv)}")
        return 2
    try:
        op = argv[0]
        num1 = float(argv[1])
        num2 = float(argv[2])
        if op == "add":
            result = num1 + num2
        elif op == "subtract":
            result = num1 - num2
        elif op == "multiply":
            result = num1 * num2
        elif op == "divide":
            if num2 == 0:
                print("error: cannot divide by zero")
                return 1
            result = num1 / num2
        else:
            print(f"error: unknown operation: {op}")
            return 2
        print(result)
        return 0
    except ValueError:
        print(f"error: {argv[1]} or {argv[2]} is not a number")
        return 2