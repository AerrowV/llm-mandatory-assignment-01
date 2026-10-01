"""In-memory todo storage. Owned by worker 1.

No HTTP here: this module must not import anything from `server.py`.
"""

from __future__ import annotations


class TodoStore:
    """Holds todos in a dict keyed by id. Ids start at 1 and are never reused.

    Edge case: `add` rejects an empty or whitespace-only title with ValueError,
    and every lookup of an unknown id returns None rather than raising.
    """

    def __init__(self) -> None:
        raise NotImplementedError("TodoStore is a stub")

    def add(self, title: str) -> dict:
        """Create a todo with done=False and return it.

        Edge case: empty or whitespace-only title raises ValueError.
        """
        raise NotImplementedError("add is a stub")

    def get(self, todo_id: int) -> dict | None:
        """Return the todo, or None if the id is unknown.

        Edge case: never raises for an unknown id.
        """
        raise NotImplementedError("get is a stub")

    def list_all(self) -> list[dict]:
        """Todos in ascending id order.

        Edge case: returns [] when empty, never None, and returns copies so a
        caller cannot mutate the store's own dicts.
        """
        raise NotImplementedError("list_all is a stub")

    def complete(self, todo_id: int) -> dict | None:
        """Mark a todo done and return it, or None if the id is unknown.

        Edge case: completing an already-complete todo is not an error.
        """
        raise NotImplementedError("complete is a stub")

    def delete(self, todo_id: int) -> bool:
        """Remove a todo. True if removed, False if the id was unknown.

        Edge case: the removed id is never reused by a later add.
        """
        raise NotImplementedError("delete is a stub")