# Local multi-LLM coding workflow

A six-role AI software team (architect, tech lead, two coders, tester, docs,
deploy validator) that runs entirely on your own machine: OpenHands agents
behind a LiteLLM proxy, on two separate local Ollama servers. The team builds a
small command-line calculator (`workspace/demo-project`) from its spec.

```bash
cp .env.example .env
python3 scripts/demo.py          # run the team (~15-20 min), then show the results
python3 scripts/demo.py --show   # show the results of the last run only
```

Setup, the two model servers and troubleshooting: [SETUP.md](SETUP.md).
Evaluation and findings: [SYNOPSIS.md](SYNOPSIS.md).

## Routing

| Endpoint | Model | Roles |
| --- | --- | --- |
| A, `127.0.0.1:11434` | `qwen2.5:3b` | architect, techlead, tester, docs, deploy-validator |
| B, `127.0.0.1:11435` | `llama3.1:8b` | coder-1, coder-2 (temperature `CODER_TEMPERATURE`) |

All settings live in `.env`; `scripts/config.py` generates
`endpoints/config.yml` and the OpenHands profiles from it on every run.

## Layout

| Path | What |
| --- | --- |
| `scripts/pipeline.py` | runs the six stages, the team chat and the fix rounds |
| `scripts/demo.py` | runs the pipeline and shows what it produced |
| `prompts/` | every instruction an agent gets, one file per role, plus `shared/` |
| `docs/`, `tickets/` | architect and tech-lead output |
| `workspace/demo-project/` | the calculator: spec (`TASK.md`), tests, the coders' code, `QUALITY.md`, `README.md` |
| `docker/validate.sh` | deployment checks, run by the deploy-validator stage |
| `artifacts/runs/` | one record per run: `run.json` and `team-chat.md` |

## Assignment

Compare local AI dev-team toolchains with at least two model endpoints.
Candidates: OpenHands (built and run here) and CrewAI (assessed, not built; see
SYNOPSIS §4).

| Person | Owns |
| --- | --- |
| 1 | OpenHands setup + endpoint wiring |
| 2 | OpenHands run + role prompts |
| 3 | CrewAI setup + endpoint wiring |
| 4 | CrewAI run + tool glue |
| 5 | Synopsis writing + peer review |
