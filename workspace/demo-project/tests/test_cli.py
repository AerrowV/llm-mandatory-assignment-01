import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from calc.cli import main  # noqa: E402


def run(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue().strip()


class TestCli(unittest.TestCase):
    def test_add_prints_whole_number(self):
        self.assertEqual(run("add", "2", "3"), (0, "5"))

    def test_divide_prints_decimal(self):
        self.assertEqual(run("divide", "5", "2"), (0, "2.5"))

    def test_unknown_operation(self):
        code, out = run("power", "2", "3")
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("error:"))

    def test_not_a_number(self):
        code, out = run("add", "two", "3")
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("error:"))

    def test_divide_by_zero(self):
        code, out = run("divide", "1", "0")
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("error:"))


if __name__ == "__main__":
    unittest.main()
