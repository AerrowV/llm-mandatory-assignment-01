"""Tests for todoapp.storage. Owned by worker 1.

Unit only: no sockets, no HTTP. `server.py` is tested separately.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from todoapp.storage import TodoStore  # noqa: E402


class TestAdd(unittest.TestCase):
    def test_returns_todo_with_expected_shape(self):
        store = TodoStore()
        todo = store.add("buy milk")
        self.assertEqual(set(todo), {"id", "title", "done"})
        self.assertEqual(todo["title"], "buy milk")
        self.assertIs(todo["done"], False)

    def test_first_id_is_one(self):
        self.assertEqual(TodoStore().add("a")["id"], 1)

    def test_ids_increment(self):
        store = TodoStore()
        self.assertEqual(store.add("a")["id"], 1)
        self.assertEqual(store.add("b")["id"], 2)
        self.assertEqual(store.add("c")["id"], 3)

    def test_empty_title_rejected(self):
        with self.assertRaises(ValueError):
            TodoStore().add("")

    def test_whitespace_title_rejected(self):
        with self.assertRaises(ValueError):
            TodoStore().add("   \t  ")


class TestGet(unittest.TestCase):
    def test_known_id(self):
        store = TodoStore()
        todo = store.add("write tests")
        self.assertEqual(store.get(todo["id"])["title"], "write tests")

    def test_unknown_id_returns_none(self):
        self.assertIsNone(TodoStore().get(42))

    def test_zero_is_not_a_valid_id(self):
        self.assertIsNone(TodoStore().get(0))


class TestListAll(unittest.TestCase):
    def test_empty_store(self):
        self.assertEqual(TodoStore().list_all(), [])

    def test_ascending_id_order(self):
        store = TodoStore()
        store.add("a")
        store.add("b")
        store.add("c")
        self.assertEqual([t["id"] for t in store.list_all()], [1, 2, 3])

    def test_returned_dicts_are_copies(self):
        store = TodoStore()
        store.add("a")
        store.list_all()[0]["title"] = "tampered"
        self.assertEqual(store.get(1)["title"], "a")

    def test_get_also_returns_a_copy(self):
        store = TodoStore()
        store.add("a")
        store.get(1)["done"] = True
        self.assertIs(store.get(1)["done"], False)


class TestComplete(unittest.TestCase):
    def test_marks_done(self):
        store = TodoStore()
        todo = store.add("a")
        self.assertIs(store.complete(todo["id"])["done"], True)

    def test_unknown_id_returns_none(self):
        self.assertIsNone(TodoStore().complete(99))

    def test_completing_twice_is_not_an_error(self):
        store = TodoStore()
        todo = store.add("a")
        store.complete(todo["id"])
        self.assertIs(store.complete(todo["id"])["done"], True)

    def test_delete_does_not_reuse_ids(self):
        store = TodoStore()
        first = store.add("a")
        store.delete(first["id"])
        self.assertEqual(store.add("b")["id"], 2)


class TestDelete(unittest.TestCase):
    def test_removes_and_returns_true(self):
        store = TodoStore()
        todo = store.add("a")
        self.assertIs(store.delete(todo["id"]), True)
        self.assertIsNone(store.get(todo["id"]))

    def test_unknown_id_returns_false(self):
        self.assertIs(TodoStore().delete(7), False)

    def test_deleting_twice_returns_false(self):
        store = TodoStore()
        todo = store.add("a")
        store.delete(todo["id"])
        self.assertIs(store.delete(todo["id"]), False)


if __name__ == "__main__":
    unittest.main()