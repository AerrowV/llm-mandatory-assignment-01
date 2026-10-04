## Setup

Python 3 standard library only, no installation required.

## Usage

To start the API, run:

```bash
python3 run.py
```

To test routes, use `curl` with the appropriate endpoint and parameters. For example:

```bash
curl -X POST -H "Content-Type: application/json" -d "{'title': 'New Task', 'description': 'Fix the bug'}" http://localhost:8000/tasks
```

## Runbook

To start the API, run:

```bash
python3 run.py
```

To stop the API, send a SIGTERM signal to the process.

To check the health of the API, send a GET request to `/health`.

The API is running on port `TODO_PORT` and can be accessed at `TODO_HOST`.

## Troubleshooting

If you encounter a port in use error, ensure no other process is using port `TODO_PORT`.

If you receive a 400 or 404 response, check the API documentation and ensure you are using the correct endpoint and parameters.

Known failures from the quality check include issues with invalid JSON payloads and missing required fields.