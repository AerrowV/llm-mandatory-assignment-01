# Setup Guide

Local multi-model agent workflow: two Ollama servers behind one LiteLLM proxy,
with OpenHands running agents against them.

No Python dependencies, no database, no build step. Standard library and Docker
only.

---

## 1. Prerequisites

| | |
| --- | --- |
| Docker Desktop | with `docker compose` v2 (`docker compose version`) |
| Ollama | installed and on `PATH` |
| Python | 3.11+ (only to run the scripts; 3.14 fine) |

## 2. Start the two model servers

The assignment requires two *separate* local model servers, not two models on
one server.

```bash
# endpoint A - default models dir
ollama serve &

# endpoint B - second server, its own models dir
mkdir -p ~/.ollama-b
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_MODELS=$HOME/.ollama-b/models ollama serve &
```

Pull the models. `architecture-model` is a chat model, `coding-model` must
support tool calling.

```bash
ollama pull qwen2.5:3b                                              # endpoint A
OLLAMA_HOST=127.0.0.1:11435 ollama pull qwen2.5-coder:7b           # endpoint B
```

Verify:

```bash
curl -s localhost:11434/api/tags | python3 -c "import json,sys;print([m['name'] for m in json.load(sys.stdin)['models']])"
curl -s localhost:11435/api/tags | python3 -c "import json,sys;print([m['name'] for m in json.load(sys.stdin)['models']])"
```

## 3. Start the stack

```bash
python3 scripts/agent.py --check
```

This one script does everything: it checks Docker and both model servers,
starts the containers, waits for the proxy to report healthy, prints the
routing table, and then hands the architect prompt to an agent. Pass a role
name or a question to run something else, or `--check` to stop after the
report and change nothing.

```bash
python3 scripts/agent.py testing              # run a different role
python3 scripts/agent.py "add a /health route" # run a custom prompt
```

Stop it with `docker compose stop`; follow logs with `docker compose logs -f openhands`.

## 4. Run a role

Prompt text lives in `prompts/`. Each file is one role.

```bash
python3 scripts/agent.py architect
python3 scripts/agent.py tech-lead
python3 scripts/agent.py implementation
python3 scripts/agent.py testing
```

The six roles are `architect`, `tech-lead`, `implementation`, `testing`,
`documentation`, `deployment`. Any other argument is treated as a literal
prompt, so you can skip the role files entirely.

Agents run with confirmation off and are given the whole repo. If you want to
watch one, the UI is at <http://localhost:8000>.

---

## How the pieces fit

```
agent  ->  OpenHands  ->  LiteLLM  ->  endpoint A :11434   architecture-model
  (role prompt)  (tool calling)   (routing)   ->  endpoint B :11435   coding-model
```

`openhands/state/profiles/*.json` binds a model name to a role. The model name
is a LiteLLM alias, and `litellm/config.yml` decides which server that alias
reaches. Changing a role's model is a one-line edit.

To move a role to the other server, edit `litellm/config.yml` and restart:

```bash
docker compose restart litellm
```

Nothing else needs rewiring — the profiles reference aliases, not servers.

## Files

| Path | Purpose |
| --- | --- |
| `docker-compose.yml` | two services: litellm, openhands |
| `litellm/config.yml` | model alias -> server routing |
| `openhands/state/profiles/*.json` | role -> model binding |
| `openhands/state/agent-profiles/default.json` | which agent runs, on which profile |
| `prompts/0*.md` | the six role prompts |
| `scripts/agent.py` | the only script: start, report, run |

There is no `settings.json`. OpenHands will happily write a 100-line one
holding a second copy of the LLM config, but the agent profile's
`llm_profile_ref` always wins, so it is dead weight — the stack runs fine
without it and the app never recreates it.

## Security

- Both model servers bind `127.0.0.1` only.
- LiteLLM and OpenHands publish to `127.0.0.1` only, so neither is reachable
  from the LAN.
- `LITELLM_MASTER_KEY=sk-local-not-secure` is a throwaway key for a loopback
  proxy. Do not reuse it anywhere real; the profiles reference the same value.
- The repo is mounted read-write at `/opt/project`, so agents can only touch
  this project.

## Known issue

Agents currently emit tool calls as **plain text** instead of structured
tool calls, so no files get written. The model produces a correct
`file_editor` call, but OpenHands does not execute it. Model, context size and
tool count have all been ruled out. See `docs/requirements-audit.md`.
