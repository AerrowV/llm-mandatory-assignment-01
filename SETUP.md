# Setup Guide

Two Ollama servers behind one LiteLLM proxy, with OpenHands running agents
against them. No Python dependencies, no database, no build step — standard
library and Docker only.

**Everything is configured in one file, `.env`.** Models, ports, role routing,
timeouts, confirmation mode, the skills deny-list. `scripts/config.py` generates
the routing file and the 14 profile files from it, so nothing is duplicated and
nothing else needs editing.

What each part is *for*, and the evidence behind the design choices, is in
`SYNOPSIS.md`. This file is only how to run it.

---

## 1. Prerequisites

| | |
| --- | --- |
| Docker Desktop | with `docker compose` v2 (`docker compose version`) |
| Ollama | installed and on `PATH` |
| Python | 3.11+ (only to run the scripts) |

## 2. Configure

```bash
cp .env.example .env      # the only setup step
```

## 3. Start the two model servers

The assignment requires two *separate* local model servers, not two models on
one server.

```bash
set -a; . ./.env; set +a          # so the variables below resolve

# endpoint A - default models dir
ollama serve &

# endpoint B - second server, its own models dir
mkdir -p ~/.ollama-b
OLLAMA_HOST="$ENDPOINT_B_HOST:$ENDPOINT_B_PORT" \
  OLLAMA_MODELS="$ENDPOINT_B_MODELS" ollama serve &
```

Pull the models. Endpoint A serves the planning roles, endpoint B the execution
roles.

```bash
set -a; . ./.env; set +a
ollama pull "$ENDPOINT_A_MODEL"
OLLAMA_HOST="$ENDPOINT_B_HOST:$ENDPOINT_B_PORT" ollama pull "$ENDPOINT_B_MODEL"
```

Check the execution model **before building anything on it**. Both endpoints must
emit *native* tool calls; a model that writes the call as prose cannot drive an
agent, and the symptom looks like a flaky model rather than a config fault.

```bash
python3 endpoints/toolcheck.py --endpoint B --stream    # expect VERDICT: PASS
python3 endpoints/toolcheck.py --endpoint A --stream
```

These read the port and model from `.env`, so they test whatever this project
actually runs. `qwen2.5-coder:7b` is a known **fail** here — it returns the call
as text.

Verify both servers are up:

```bash
curl -s "$ENDPOINT_A_URL/api/tags" | python3 -c "import json,sys;print([m['name'] for m in json.load(sys.stdin)['models']])"
curl -s "$ENDPOINT_B_URL/api/tags" | python3 -c "import json,sys;print([m['name'] for m in json.load(sys.stdin)['models']])"
```

## 4. Start the stack

```bash
python3 scripts/agent.py --check     # report only: endpoints, containers, routing
python3 scripts/agent.py              # regenerate config, start containers,
                                     # wait healthy, print routing, run a role
```

`agent.py` takes an optional role name or a literal prompt (§5), plus
`--confirm`, `--workers`, `--merge`, `--budget`, `--max-iterations`. With no
role it runs the architect. Any unrecognised word is treated as a literal
prompt, so there is no `up`/`down`/`status` subcommand — use `--check` to report
and `docker compose` to stop.

Stop with `docker compose stop`. Logs: `docker compose logs -f openhands`.
UI: <http://localhost:8000/canvas>.

**After editing `.env` or `endpoints/config.yml`, restart the proxy** — its
config is read once, at startup:

```bash
docker compose restart litellm
```

## 5. Run a role

Prompt text lives in `prompts/`, one file per role. Edit a prompt, never a
profile: the prompt is the only place role behaviour is written down.

```bash
python3 scripts/promptcheck.py          # prompts well-formed, ~1s
python3 scripts/promptcheck.py --live   # also ask each role's model to act on it

python3 scripts/agent.py architect      # or: techlead, coder-1, coder-2,
                                        #     tester, docs, deploy-validator
python3 scripts/agent.py "add a /health route"   # any other arg is a literal prompt
```

`coder-1` and `coder-2` are the two parallel workers: they share one
implementation prompt and differ only by name, so the pipeline can point each at
its own git worktree.

### Confirmation mode

```bash
python3 scripts/agent.py --confirm never  architect   # unattended (default)
python3 scripts/agent.py --confirm risky  coder-1     # ask before commands
python3 scripts/agent.py --confirm always architect    # ask before every action
```

`never` is the only mode an unattended pipeline can use, because OpenHands
headless mode is always-approve. To satisfy the other branch of the
predictability requirement — plan and diffs reviewed before execution — run with
`--confirm never` and let each worker commit to its own branch; the diffs are the
review surface. Both branches are measured in `SYNOPSIS.md` §6.1.

## 6. Run the pipeline

This is the deliverable demo. It runs the six stages in order and checks the
artifacts each one was supposed to leave behind.

```bash
python3 scripts/pipeline.py --stages coder-1 --budget 1500   # the blocking stage
python3 scripts/pipeline.py --stages architect,techlead
python3 scripts/pipeline.py --check                          # stack preflight
python3 scripts/pipeline.py --compare RUN_A RUN_B            # NFR2, two runs
```

Stages: `architect` → `techlead` → `coder-1`,`coder-2` → `tester` → `docs` →
`deploy-validator`. Each writes to `artifacts/runs/<id>/`, recording per-stage
status, the routing `.env` produced, and the verification result.

For a single-task end-to-end check with a pass/fail exit code:

```bash
python3 scripts/demo.py            # preflight, smoke test, one task, verify
python3 scripts/demo.py --check    # preflight only
python3 scripts/demo.py --smoke    # tool-calling smoke test only
```

## 7. Deployability validation

```bash
./docker/validate.sh          # 13 checks, grouped; --list to see them
./docker/validate.sh --list
```

Covers config validity, the security baseline, the demo project building and
testing, and the live stack serving all seven aliases.

## 8. How the pieces fit

```
.env                                    the only file to edit
  |
  +-> endpoints/config.yml              generated: alias -> api_base + model
  |     -> endpoint A   architect, techlead, docs
  |     -> endpoint B   coder-1, coder-2, tester, deploy-validator
  |
  +-> openhands/state/profiles/<role>.json        generated: role -> "openai/<alias>"
  +-> openhands/state/agent-profiles/<role>.json  generated: which agent runs

prompts/<NN>-<role>.md   the role's instructions, read at run time
```

Each role has its own agent profile and LLM profile, and the LLM profile names a
**LiteLLM alias, never a server**. So does the prompt. Nothing in the prompt or
profile layer names a host or a model, so moving a role between endpoints is a
`.env` edit plus a proxy restart.

Inspect what `.env` resolves to without starting anything:

```bash
python3 scripts/config.py          # regenerate, and print the routing
python3 scripts/config.py --check  # report drift, write nothing
```

## 9. Files

| Path | Purpose | Edit it? |
| --- | --- | --- |
| `.env` | every setting: models, ports, routing, timeouts, skills | **yes, this one** |
| `.env.example` | documented template for the above | to document |
| `prompts/0*.md` | one prompt per role | yes |
| `prompts/fragments/*.md` | shared preamble a worktree worker gets | yes |
| `scripts/config.py` | `.env` → routing + 14 profile files | rarely |
| `scripts/agent.py` | start/stop/status, run one role | rarely |
| `scripts/pipeline.py` | the six stages, with artifact checks | rarely |
| `scripts/promptcheck.py` | are the prompts well-formed? | rarely |
| `scripts/demo.py` | the end-to-end demo and its verdict | rarely |
| `scripts/conversation.py` | what did an agent actually do | rarely |
| `docker/validate.sh` | the deployability checks | rarely |
| `docker-compose.yml` | two services: litellm, openhands | rarely |
| `endpoints/config.yml` | alias → server routing | **generated** |
| `openhands/state/profiles/<role>.json` | role → LiteLLM alias | **generated** |
| `openhands/state/agent-profiles/<role>.json` | which agent runs | **generated** |
| `endpoints/toolcheck.py` | is this model tool-call capable? | no |
| `endpoints/thinkcheck.py` | does it emit thinking tokens, how many | no |

Generated files are committed so a fresh clone works before anything runs, and
are rewritten from `.env` by `scripts/agent.py` on every run. A hand edit is
lost; change `.env`. `docker/validate.sh` fails on drift.

## 10. If something breaks

Every fault below is **silent**: the process exits 0 or the proxy answers 200
while the agent does nothing. `SYNOPSIS.md` §4.4 has the full table with
detection method; the short version:

| Symptom | Cause | Check |
|---|---|---|
| Agent plans but writes nothing | model emits the tool call as prose | `endpoints/toolcheck.py` |
| Every turn `400 "No connected db."` | a `master_key` or `os.environ/…` crept in | `docker/validate.sh` |
| Agent answers with unrelated text | prompt silently truncated | token floor in `.env` |
| `fatal: not a git repository` in the agent | worktree `.git` pointer absolute | `--relative-paths` is already set |
| Agent invokes a frontend skill for a backend task | skills auto-load | `DISABLED_SKILLS` in `.env` |
| Alias missing from `/v1/models` | proxy config not reloaded | `docker compose restart litellm` |

Two rough edges that are not wiring faults:

- `enabled_skills: []` does **not** disable skills; they are injected regardless.
  Use the `DISABLED_SKILLS` deny-list in `.env`.
- `file_editor` rejects relative paths. The model often tries one, eats an
  `Invalid path parameter`, then recovers via `terminal`. Naming the absolute
  path in the prompt avoids the wasted turn — every prompt does this already.

## 11. Security

- Both model servers bind `127.0.0.1` only.
- LiteLLM and OpenHands publish to `127.0.0.1` only, so neither is reachable
  from the LAN. Verified by probing the LAN address; all four ports refuse.
- The proxy key lives in `.env`, which is gitignored, and reaches the proxy
  through `env_file`. Without a valid key `/v1/models` returns 401.
- The key is also written literally into the generated LLM profiles, because
  OpenHands does not expand `os.environ/` references in that field. Safe only
  while every port stays on `127.0.0.1`; `docker/validate.sh` fails the build if
  a port is published on all interfaces.
- The repo is mounted read-write at `/opt/project`, so agents only touch this
  project.
