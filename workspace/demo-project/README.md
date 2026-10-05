## Setup

Python 3 standard library only, no installation required.

## Usage

### Start the API
```bash
python3 run.py start
```

### Test the API
```bash
curl -X GET http://localhost:5000/tasks
```

## Runbook

### Start
```bash
curl -X POST http://localhost:5000/start
```

### Stop
```bash
curl -X POST http://localhost:5000/stop
```

### Health Check
```bash
curl http://localhost:5000/health
```

## Troubleshooting

### Port in Use
If you get a `400 Bad Request` error, ensure the port is not in use.

### 404 Not Found
If you get a `404 Not Found` error, ensure the API is running and the endpoint is correct.

### Known Failures
- API not responding: Ensure the API is running and the port is not in use.
- API returns 400: Ensure the API is running and the port is not in use.
- API returns 404: Ensure the API is running and the port is not in use.
