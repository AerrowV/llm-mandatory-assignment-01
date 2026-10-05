
import json
from todoapp.storage import TodoStore

class TodoServer:
    def __init__(self, store: TodoStore, host: str = "127.0.0.1",
                 port: int = 8765) -> None:
        self.store = store
        self.host = host
        self.port = port

    def handle(self, method: str, path: str, body: bytes | None = None) -> tuple[int, dict]:
        if method == "GET" and path == "/health":
            return 200, {'status': 'ok'}
        elif method == "GET" and path == "/todos":
            todos = self.store.list_all()
            return 200, {'todos': todos}
        elif method == "POST" and path == "/todos":
            if body is not None:
                try:
                    todo = json.loads(body.decode())
                    if todo['title'] == "":
                        return 400, {'error': 'Title is required'}
                    elif not isinstance(todo['title'], str):
                        return 400, {'error': 'Title must be a string'}
                    else:
                        new_todo = self.store.add(todo['title'])
                        return 201, new_todo
                except json.JSONDecodeError:
                    return 400, {'error': 'Invalid JSON'}
            else:
                return 400, {'error': 'Missing title'}
        elif method == "GET" and path.startswith("/todos/"):
            try:
                todo_id = int(path.split('/')[-1])
                todo = self.store.get(todo_id)
                if todo is not None:
                    return 200, todo
                else:
                    return 404, {'error': 'Unknown todo id'}
            except ValueError:
                return 404, {'error': 'Invalid todo id'}
        elif method == "DELETE" and path.startswith("/todos/"):
            try:
                todo_id = int(path.split('/')[-1])
                self.store.delete(todo_id)
                return 204, {}
            except ValueError:
                return 404, {'error': 'Unknown todo id'}
        else:
            return 405, {'error': 'Method not allowed'}

    def start(self) -> None:
        pass
