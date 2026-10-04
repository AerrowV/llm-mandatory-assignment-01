class TodoServer:
    def __init__(self, store: TodoStore, host: str = "127.0.0.1",
                 port: int = 8765) -> None:
        self.store = store
        self.host = host
        self.port = port

    def handle(self, method: str, path: str, body: bytes | None = None) -> tuple[int, dict]:
        if method == "GET" and path == "/health":
            return 200, {"status": "ok"}
        elif method == "GET" and path == "/todos":
            todos = self.store.list_all()
            return 200, {"todos": todos}
        elif method == "POST" and path == "/todos":
            todo = self.store.add(body.decode())
            return 201, todo
        elif method == "GET" and path.startswith("/todos/"):
            todo_id = int(path.split("/")[-1])
            todo = self.store.get(todo_id)
            return 200, todo
        elif method == "DELETE" and path.startswith("/todos/"):
            todo_id = int(path.split("/")[-1])
            self.store.delete(todo_id)
            return 204, {}
        else:
            return 405, {}

    def start(self) -> None:
        pass