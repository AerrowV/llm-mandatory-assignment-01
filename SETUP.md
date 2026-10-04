# Setup Guide

OpenHands agents run six roles against two separate local Ollama servers,
through one LiteLLM proxy. Everything is configured in `.env`.

## 1. Prerequisites

- Docker Desktop (with `docker compose`)
- Ollama
- Python 3.11+ (standard library only)

## 2. Start the two model endpoints

Two separate Ollama servers, each with its own port and model directory:

```bash
ollama serve &                                             # endpoint A, :11434
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_MODELS=~/.ollama-b/models ollama serve &   # endpoint B

ollama pull qwen2.5:3b                                     # endpoint A model
OLLAMA_HOST=127.0.0.1:11435 ollama pull llama3.1:8b        # endpoint B model
```

## 3. Configure the toolchain

```bash
cp .env.example .env
```

`.env` decides which model each endpoint serves and which roles run on it:

```
ENDPOINT_A_ROLES=architect,techlead,docs
ENDPOINT_B_ROLES=coder-1,coder-2,tester,deploy-validator
```

To move a role, change these lines; the pipeline regenerates
`endpoints/config.yml` and the OpenHands profiles from `.env` on every run
(after editing `.env` by hand, also run `docker compose restart litellm`).

## 4. Run the demo workflow

```bash
python3 scripts/pipeline.py
```

This starts LiteLLM and OpenHands (`docker compose up -d`), then runs:

| Stage | Role | Output |
| --- | --- | --- |
| FR1 | architect | `docs/components.md`, `api.md`, `deployment.md`, `decisions.md`, `handoff.md` |
| FR2 | techlead | `tickets/list.md` + one file per ticket |
| FR3 | coder-1, coder-2 in parallel | `storage.py` and `server.py` in `workspace/demo-project`, each on its own git branch |
| FR4 | tester | runs the tests, writes `workspace/demo-project/QUALITY.md` |
| FR5 | docs | `workspace/demo-project/README.md` |
| FR6 | deploy-validator | runs `docker/validate.sh`, writes `docs/deployment-validation.md` |

Each stage's files are checked before the next stage starts. A record of the run
is written to `artifacts/runs/<timestamp>/run.json`. Watch the agents live at
<http://localhost:8000>.

Other commands:

```bash
python3 scripts/pipeline.py --check                  # check endpoints and stack only
python3 scripts/pipeline.py --from tester            # resume at a stage
python3 scripts/pipeline.py --compare RUN_A RUN_B    # compare two runs
./docker/validate.sh                                 # deployment checks on their own
git diff main agent/coder-1                          # review a worker's changes
```

Set `CONFIRMATION=risky` in `.env` to make OpenHands ask before running
commands.

## 5. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `endpoint A/B` fails in preflight | start that `ollama serve` (step 2) |
| an alias is missing in LiteLLM | `docker compose restart litellm` |
| a stage stops with "did not deliver" | rerun it: `python3 scripts/pipeline.py --from <role>` |
| an agent writes text instead of calling tools | the model cannot do tool calls; pick another in `.env` |

Stop everything with `docker compose down`.
