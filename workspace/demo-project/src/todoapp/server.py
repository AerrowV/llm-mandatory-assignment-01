"""HTTP layer for the todo API. Owned by worker 2.

Import TodoStore from `todoapp.storage`; do not reimplement storage here.
"""

from __future__ import annotations


class TodoServer:
    """Serves the todo API over HTTP.

    `handle` is the entire HTTP contract and is unit-testable without binding a
    socket. `start` serves it.

    Edge case: GET /health always returns 200 without touching the store, and
    any error path returns a JSON {"error": ...} body rather than a traceback.
    """

    def __init__(self, store, host: str = "127.0.0.1", port: int = 8765) -> None:
        raise NotImplementedError("TodoServer is a stub")

    def handle(self, method: str, path: str, body: bytes | None = None) -> tuple[int, dict]:
        """Route one request. Returns (status_code, json_body).

        Edge case: 204 responses carry an empty body dict; malformed JSON input
        is a 400, not a 500.
        """
        raise NotImplementedError("handle is a stub")

    def start(self) -> None:
        """Serve until interrupted.

        Edge case: binding failure surfaces as a clear message, not a hang.
        """
        raise NotImplementedError("start is a stub")