
import json
from storage import TodoStore

class TodoServer:
    def __init__(self, store: TodoStore, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.store = store
        self.host = host
        self.port = port

    def handle(self, method: str, path: str, body: bytes | None = None) -> tuple[int, dict]:
        if method == "GET" and path == "/health":
            return 200, {"status": "ok"}
        elif method == "GET" and path == "/todos":
            todos = self.store.list_all()
            return 200, {"todos": [todo for todo in todos]}
        elif method == "POST" and path == "/todos":
            try:
                todo = json.loads(body.decode())
                if not todo or not isinstance(todo, dict) or "title" not in todo or not isinstance(todo["title"], str):
                    return 400, {"error": "Invalid request body"}
                if not todo["title"]:
                    return 400, {"error": "Empty title"}
                todo_id = self.store.add(todo["title"])
                return 201, {"todo": {"id": todo_id, "title": todo["title"], "done": False}}
            except json.JSONDecodeError:
                return 400, {"error": "Malformed JSON request body"}
        elif method == "GET" and path.startswith("/todos/"):
            try:
                todo_id = int(path.split("/")[-1])
                todo = self.store.get(todo_id)
                if todo is None:
                    return 404, {"error": "Unknown todo id"}
                return 200, {"todo": todo}
            except ValueError:
                return 404, {"error": "Unknown todo id"}
        elif method == "DELETE" and path.startswith("/todos/"):
            try:
                todo_id = int(path.split("/")[-1])
                if self.store.delete(todo_id):
                    return 204, {}
                return 404, {"error": "Unknown todo id"}
            except ValueError:
                return 404, {"error": "Unknown todo id"}
        else:
            return 405, {"error": "Method not allowed"}

    def start(self) -> None:
        import socketserver
        with socketserver.TCPServer((self.host, self.port), self.handle) as server:
            server.serve_forever()
