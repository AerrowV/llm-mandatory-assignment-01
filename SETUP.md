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

## 5. Run the demo

`scripts/demo.py` runs the whole thing end to end and says whether it worked.

```bash
python3 scripts/demo.py            # preflight, smoke test, one task, verify
python3 scripts/demo.py --check    # preflight only, change nothing
python3 scripts/demo.py --smoke    # tool-calling smoke test only
```

Four phases: preflight (both endpoints, both containers, routing), smoke test
(a structured tool call straight through LiteLLM, no agent), one demo run, then
verify — which counts the tools the agent actually executed and checks the
artifact landed. Each run drops a JSON summary in `artifacts/runs/<timestamp>/`.

Exit code is 0 only when the agent executed tools *and* wrote the file, so it
can gate a script.

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
| `scripts/agent.py` | start, report, run one role |
| `scripts/demo.py` | the end-to-end demo and its verdict |

There is no `settings.json`. OpenHands will happily write a 100-line one
holding a second copy of the LLM config, but the agent profile's
`llm_profile_ref` always wins, so it is dead weight — the stack runs fine
without it and the app never recreates it.

## Four things that silently break agents

All four cost real debugging time, so `demo.py` checks them.

**0. No database.** LiteLLM must not have a `DATABASE_URL`, and
`store_model_in_db` must stay `false`. With a database attached, LiteLLM treats
the model list as DB-backed state while still only loading the router from
`litellm/config.yml` at startup. The two drift apart, `/v1/models` silently
drops aliases, and every agent request fails with
`Invalid model name passed in model=<alias>` — which looks like a missing model
but is not. There is no `db` service in `docker-compose.yml` for this reason.

Because the config file is read once, at startup, **restart litellm after every
edit to `litellm/config.yml`**:

```bash
docker compose up -d litellm     # recreate, picks up compose changes
docker compose restart litellm   # plain restart, picks up config.yml changes
```

Confirm the aliases you expect are actually served before blaming a model:

```bash
curl -s localhost:4000/v1/models -H "Authorization: Bearer sk-local-not-secure"
```

**1. Route to ollama's `/v1` endpoint as `openai/<model>`, not `ollama_chat/`.**
This is the one that makes agents unusable, and it is silent. LiteLLM's
`ollama_chat` handler translates ollama's native tool calls into the OpenAI wire
format and emits **every parallel call under `index=0`**, concatenating the
argument fragments into one unparseable string:

```
{"path": "docs/a.md", "text": "a"}{"path": "docs/b.md", "text": "b"}
```

OpenHands rejects that with `Error validating tool '...': Extra data: ...
unparseable JSON`, the turn dies, and the agent replies with a plan in prose
instead of acting. It looks like a flaky weak model, because it only fires when
the model happens to emit two tool calls at once. Measured on `qwen2.5:3b`:
`ollama_chat/` merged 2 valid calls into 1 broken one; `openai/` against
`http://host.docker.internal:11434/v1` returned `index=0` and `index=1`, each
valid. Both aliases are configured that way.

Do not "fix" this by turning streaming off — OpenHands hard-forces
`stream: true` on every launch (`conversation_service.py`, the `settings_config`
copy), so `stream: false` in a profile is ignored.

**2. Declare a context window the request fits in.** One agent request is ~20k
tokens (39k chars of system prompt plus 21 tool definitions). LiteLLM silently
truncates the prompt to the declared `max_input_tokens`, and the model then
ignores its task entirely and answers with unrelated text. Both aliases declare
32768. `demo.py --check` prints this budget.

**3. The model must emit native tool calls.** Measured against ollama directly,
bypassing LiteLLM: `qwen2.5:3b` returns `message.tool_calls` in both streaming
and non-streaming mode; `qwen2.5-coder:7b` returns the call as *text* in both
modes, on either endpoint. The agent profile is therefore bound to
`architecture` (`qwen2.5:3b`); `coding-model` is routed and healthy but is not
tool-call capable, so it cannot drive an agent. Pulling a different model onto
endpoint B does not change this unless the model itself was tool-trained — use
`qwen2.5:7b-instruct`, `qwen3:8b` or `qwen2.5-coder:32b-instruct` if endpoint B
has to run real agent turns.

## Security

- Both model servers bind `127.0.0.1` only.
- LiteLLM and OpenHands publish to `127.0.0.1` only, so neither is reachable
  from the LAN.
- `LITELLM_MASTER_KEY=sk-local-not-secure` is a throwaway key for a loopback
  proxy. Do not reuse it anywhere real; the profiles reference the same value.
- The repo is mounted read-write at `/opt/project`, so agents can only touch
  this project.

## Known issue

None blocking a demo run. `qwen2.5-coder:7b` on endpoint B does not emit native
tool calls, so coding work currently runs on endpoint A; see item 4 above.

Two smaller rough edges, neither of them wiring faults:

- OpenHands auto-loads 66 skills, and the agent often spends a turn calling
  `invoke_skill` on a frontend/design skill for tasks that need none. That burns
  tokens and derails a 3b model. Turning skills off makes runs more predictable.
- `file_editor` requires absolute paths. The model frequently passes a relative
  one, eats an `Invalid path parameter` observation, then recovers via
  `terminal`. Naming the absolute path in the task prompt avoids the wasted turn.
