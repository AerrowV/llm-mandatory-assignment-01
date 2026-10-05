
import uuid

class TodoStore:
    def __init__(self) -> None:
        self.todos = {}

    def add(self, title: str) -> dict:
        if not title:
            raise ValueError('Title cannot be empty')
        todo_id = len(self.todos) + 1
        self.todos[todo_id] = {'id': todo_id, 'title': title, 'done': False}
        return self.todos[todo_id]

    def get(self, todo_id: int) -> dict | None:
        return self.todos.get(todo_id)

    def list_all(self) -> list[dict]:
        return list(self.todos.values())

    def complete(self, todo_id: int) -> dict | None:
        todo = self.get(todo_id)
        if todo:
            todo['done'] = True
            return todo
        return None

    def delete(self, todo_id: int) -> bool:
        return self.todos.pop(todo_id, None) is not None
