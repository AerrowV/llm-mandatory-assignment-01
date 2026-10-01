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

Pull the models. Endpoint A serves the planning roles, endpoint B the execution
roles. **Both must emit native tool calls** — a model that writes the call as
prose cannot drive an agent, and the symptom looks like a flaky model rather
than a config fault. See failure mode 3.

```bash
ollama pull qwen2.5:3b                                              # endpoint A
OLLAMA_HOST=127.0.0.1:11435 ollama pull qwen3:8b                   # endpoint B
```

Then check the endpoint B model before building anything on it:

```bash
python3 endpoints/toolcheck.py --port 11435 --model qwen3:8b --stream
```

Expect `VERDICT: PASS`. `qwen2.5-coder:7b` is a known **fail** here — it returns
the call as text — and `qwen2.5:7b-instruct` is a verified alternative.

Verify both servers:

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
python3 scripts/agent.py tester                # run a different role
python3 scripts/agent.py "add a /health route" # run a custom prompt
```

Stop it with `docker compose stop`; follow logs with `docker compose logs -f openhands`.

## 4. Run a role

Prompt text lives in `openhands/prompts/`. Each file is one role.

```bash
python3 scripts/agent.py architect
python3 scripts/agent.py techlead
python3 scripts/agent.py tester
python3 scripts/agent.py docs
python3 scripts/agent.py deploy-validator
```

The roles are `architect`, `techlead`, `coder-1`, `coder-2`, `tester`, `docs`,
`deploy-validator`. `coder-1` and `coder-2` are the two parallel workers: they
share the one implementation prompt and differ only in name, so the pipeline
can point each at its own git worktree. Any other argument is treated as a
literal prompt, so you can skip the role files entirely.

### Confirmation mode

The assignment's predictability requirement wants a control mechanism. The
policy is per-run:

```bash
python3 scripts/agent.py --confirm never  architect   # unattended (default)
python3 scripts/agent.py --confirm risky  coder-1     # ask before commands
python3 scripts/agent.py --confirm always architect    # ask before every action
```

`never` is the only mode an unattended pipeline can use. `risky` gates shell
commands and destructive file operations, which is the closest thing this
version offers to ask-before-run. To satisfy the *other* branch of the
requirement — plan and diffs reviewed before execution — run with `--confirm
never` and let each worker commit to its own branch; the diffs are the review
surface.

Agents are given the whole repo. The UI is at <http://localhost:8000>.

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
role prompt (openhands/prompts/NN-*.md)
  -> agent profile  openhands/state/agent-profiles/<role>.json
  -> LLM profile    openhands/state/profiles/<role>.json   -> "openai/<alias>"
  -> LiteLLM alias  endpoints/config.yml                   -> api_base + model
  -> endpoint A :11434   architect, techlead, docs
  -> endpoint B :11435   coder-1, coder-2, tester, deploy-validator
```

Each role has its own agent profile and LLM profile, and the LLM profile names
a **LiteLLM alias, never a server**. `endpoints/config.yml` alone decides which
physical endpoint an alias reaches, so moving a role between endpoints is a
one-line edit there — no rewiring in any toolchain.

To move a role to the other server, edit `endpoints/config.yml` and restart:

```bash
docker compose restart litellm
```

Nothing else needs rewiring — the profiles reference aliases, not servers.

## Files

| Path | Purpose |
| --- | --- |
| `docker-compose.yml` | two services: litellm, openhands |
| `endpoints/config.yml` | model alias -> server routing (shared by both toolchains) |
| `endpoints/.env` | the proxy key and both model servers' addresses (gitignored) |
| `endpoints/.env.example` | documented template for the above |
| `endpoints/toolcheck.py` | is this model actually tool-call capable? |
| `openhands/prompts/0*.md` | the role prompts |
| `openhands/state/profiles/<role>.json` | role -> LiteLLM alias |
| `openhands/state/agent-profiles/<role>.json` | which agent runs, on which LLM profile |
| `scripts/agent.py` | start, report, run one role |
| `scripts/demo.py` | the end-to-end demo and its verdict |

### Path mapping

The layout targets a shared endpoint layer, so a few paths differ from earlier
versions of this repo:

| Now | Was |
| --- | --- |
| `endpoints/` | `litellm/` |
| `openhands/prompts/` | `prompts/` |
| `openhands/state/profiles/<role>.json` | `profiles/{architecture,coding}.json` |
| `openhands/state/agent-profiles/<role>.json` | `agent-profiles/default.json` |
| `endpoints/config.yml` | `litellm/config.yml` |

There is no `settings.json`. OpenHands will happily write a 100-line one
holding a second copy of the LLM config, but the agent profile's
`llm_profile_ref` always wins, so it is dead weight — the stack runs fine
without it and the app never recreates it.

## Four things that silently break agents

All four cost real debugging time, so `demo.py` checks them.

**0. No database.** LiteLLM must not have a `DATABASE_URL`, and
`store_model_in_db` must stay `false`. With a database attached, LiteLLM treats
the model list as DB-backed state while still only loading the router from
`endpoints/config.yml` at startup. The two drift apart, `/v1/models` silently
drops aliases, and every agent request fails with
`Invalid model name passed in model=<alias>` — which looks like a missing model
but is not. There is no `db` service in `docker-compose.yml` for this reason.

Because the config file is read once, at startup, **restart litellm after every
edit to `endpoints/config.yml`**:

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

**3. The model must emit native tool calls.** A model can answer a chat message
perfectly and still be useless to an agent: if it returns the call as a *string
in `content`* instead of in `message.tool_calls`, OpenHands never executes
anything and the agent narrates a plan instead of acting.

Measured with `endpoints/toolcheck.py`, which asks for one tool call and reports
where it came back — first directly against the model server, then again through
the proxy with `fallbacks` disabled, so a pass cannot be borrowed from another
alias:

| Model | Endpoint | Direct | Through proxy |
| --- | --- | --- | --- |
| `qwen2.5:3b` | A | native, both modes | native (`architect`) |
| `qwen2.5-coder:7b` | B | **text, both modes** | **text** (`coder-1`) |
| `qwen3:8b` | B | native, both modes | native (`coder-1`) |
| `qwen2.5:7b-instruct` | B | native, both modes | native (`coder-1`) |

The model is the variable here, not the server. `qwen2.5-coder:7b` returns
`{"name": "write_file", "arguments": {...}}` as prose. All three tool-trained
candidates pass, so **both endpoints can run real agent turns** — which is what
the multi-endpoint requirement is actually asking for. The earlier arrangement
had a single agent profile bound to `qwen2.5:3b`, so every role silently ran on
endpoint A and endpoint B carried no real traffic.

Reproduce before trusting any model on endpoint B:

```bash
python3 endpoints/toolcheck.py --port 11435 --model <model> --stream
python3 endpoints/toolcheck.py --via-proxy --model coder-1 --stream
```

Note the asymmetry with the LiteLLM docs, which recommend `ollama_chat/` for
tool calling. That is fine for a single call and breaks this workload; see
item 1.

## Security

- Both model servers bind `127.0.0.1` only.
- LiteLLM and OpenHands publish to `127.0.0.1` only, so neither is reachable
  from the LAN.
- The proxy key lives in `endpoints/.env`, which is gitignored. It is referenced
  by `general_settings.master_key` in `endpoints/config.yml` and by every LLM
  profile through `os.environ/LITELLM_MASTER_KEY`, so no key is committed or
  hardcoded in `docker-compose.yml`. `endpoints/.env.example` documents the
  variable with a placeholder. Without a valid key `/v1/models` returns 401.
- The repo is mounted read-write at `/opt/project`, so agents can only touch
  this project.

## Known issue

None blocking a demo run. The one that mattered — endpoint B being unable to
drive an agent — is resolved by model choice, not by rewiring; see item 3 and
`docs/evaluation-openhands.md` for the measurement table.

Two smaller rough edges, neither of them wiring faults:

- OpenHands auto-loads 66 skills, and the agent often spends a turn calling
  `invoke_skill` on a frontend/design skill for tasks that need none. That burns
  tokens and derails a 3b model. Turning skills off makes runs more predictable.
- `file_editor` requires absolute paths. The model frequently passes a relative
  one, eats an `Invalid path parameter` observation, then recovers via
  `terminal`. Naming the absolute path in the task prompt avoids the wasted turn.
