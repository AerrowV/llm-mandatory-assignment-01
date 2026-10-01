#!/usr/bin/env python3
"""Entry point for the todo API. Already written; do not edit.

    PYTHONPATH=src python3 run.py
    curl 127.0.0.1:8765/health
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from todoapp.server import TodoServer  # noqa: E402
from todoapp.storage import TodoStore  # noqa: E402


def main() -> int:
    host = os.environ.get("TODO_HOST", "127.0.0.1")
    port = int(os.environ.get("TODO_PORT", "8765"))
    server = TodoServer(TodoStore(), host=host, port=port)
    print(f"todo api listening on http://{host}:{port}", flush=True)
    server.start()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
        sys.exit(0)