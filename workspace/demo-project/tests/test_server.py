"""Tests for todoapp.server. Owned by worker 2.

These drive `handle` directly, so no socket is bound and no port is needed.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from todoapp.server import TodoServer  # noqa: E402
from todoapp.storage import TodoStore  # noqa: E402


def body(payload):
    return json.dumps(payload).encode()


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.store = TodoStore()
        self.server = TodoServer(self.store)


class TestHealth(ServerCase):
    def test_returns_200_ok(self):
        status, payload = self.server.handle("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok"})

    def test_works_before_any_todo_exists(self):
        status, payload = self.server.handle("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")


class TestListAndCreate(ServerCase):
    def test_list_empty(self):
        status, payload = self.server.handle("GET", "/todos")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"todos": []})

    def test_create_returns_201_and_the_todo(self):
        status, payload = self.server.handle("POST", "/todos", body({"title": "buy milk"}))
        self.assertEqual(status, 201)
        self.assertEqual(payload["title"], "buy milk")
        self.assertIs(payload["done"], False)

    def test_created_todo_appears_in_list(self):
        self.server.handle("POST", "/todos", body({"title": "buy milk"}))
        status, payload = self.server.handle("GET", "/todos")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["todos"]), 1)

    def test_create_without_title_is_400(self):
        status, payload = self.server.handle("POST", "/todos", body({}))
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_create_with_non_string_title_is_400(self):
        status, payload = self.server.handle("POST", "/todos", body({"title": 42}))
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_create_with_empty_title_is_400(self):
        status, _ = self.server.handle("POST", "/todos", body({"title": ""}))
        self.assertEqual(status, 400)

    def test_create_with_whitespace_title_is_400(self):
        status, _ = self.server.handle("POST", "/todos", body({"title": "   "}))
        self.assertEqual(status, 400)

    def test_malformed_json_is_400(self):
        status, payload = self.server.handle("POST", "/todos", b"{not json")
        self.assertEqual(status, 400)
        self.assertIn("error", payload)


class TestGetOne(ServerCase):
    def test_known_id(self):
        todo = self.store.add("buy milk")
        status, payload = self.server.handle("GET", f"/todos/{todo['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(payload["title"], "buy milk")

    def test_unknown_id_is_404(self):
        status, payload = self.server.handle("GET", "/todos/999")
        self.assertEqual(status, 404)
        self.assertIn("error", payload)

    def test_non_numeric_id_is_404_not_400(self):
        status, payload = self.server.handle("GET", "/todos/abc")
        self.assertEqual(status, 404)
        self.assertIn("error", payload)


class TestDelete(ServerCase):
    def test_returns_204_with_empty_body(self):
        todo = self.store.add("buy milk")
        status, payload = self.server.handle("DELETE", f"/todos/{todo['id']}")
        self.assertEqual(status, 204)
        self.assertEqual(payload, {})

    def test_unknown_id_is_404(self):
        status, payload = self.server.handle("DELETE", "/todos/999")
        self.assertEqual(status, 404)
        self.assertIn("error", payload)


class TestMethodAndPathErrors(ServerCase):
    def test_wrong_method_on_known_path_is_405(self):
        status, payload = self.server.handle("POST", "/todos/1", body({}))
        self.assertEqual(status, 405)
        self.assertIn("error", payload)

    def test_wrong_method_on_health_is_405(self):
        status, _ = self.server.handle("DELETE", "/health")
        self.assertEqual(status, 405)

    def test_unknown_path_is_404(self):
        status, payload = self.server.handle("GET", "/nope")
        self.assertEqual(status, 404)
        self.assertIn("error", payload)


class TestCompleteRoute(ServerCase):
    def test_marks_done(self):
        todo = self.store.add("buy milk")
        status, payload = self.server.handle("POST", f"/todos/{todo['id']}/complete")
        self.assertEqual(status, 200)
        self.assertIs(payload["done"], True)

    def test_unknown_id_is_404(self):
        status, _ = self.server.handle("POST", "/todos/999/complete")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()