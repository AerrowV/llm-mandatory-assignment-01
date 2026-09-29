# Requirements Audit

Audited against `Assignment LLm for developers.pdf` (4 pages).
Date: 2026-09-28

Status legend: **MET** / **PARTIAL** / **NOT MET** / **BLOCKED**

---

## Hard Requirements

### 1. Multiple local endpoints — MET

| | |
| --- | --- |
| Endpoint A | ollama on `127.0.0.1:11434` — `qwen2.5:3b` |
| Endpoint B | ollama on `127.0.0.1:11435`, separate `OLLAMA_MODELS` dir — `qwen2.5-coder:7b` |

Two genuinely separate server processes/ports, so this satisfies "two different
local LLM servers/hosts", not just two models on one server.

Switching/routing is configuration-only, via `litellm/config.yml`:

| model_name | routes to | role |
| --- | --- | --- |
| `architecture-model` | A / qwen2.5:3b | planning and documentation, chat only |
| `coding-model` | **B** / qwen2.5-coder:7b | main coding worker, tool calling |

Role→model binding is a one-line edit in `openhands/state/profiles/*.json`.
Those profiles are plain JSON and committed, so a fresh clone reproduces the
setup. Adding an endpoint is a `model_list` entry in `litellm/config.yml` plus
`docker compose restart litellm`; no rewiring elsewhere.

### 2. Open source — MET

LiteLLM, OpenHands and Ollama are all open source.

---

## Functional Requirements

All six role prompts exist in `prompts/`, but **no agent has successfully
produced an artifact yet** (see BLOCKER). Output files are all 0 bytes.

| # | Responsibility | Status | Evidence / gap |
| --- | --- | --- | --- |
| 1 | Architecture | NOT MET | `prompts/01-architect.md` exists; `docs/components.md`, `api.md`, `deployment.md`, `decisions.md` all 0 bytes |
| 2 | Tech lead | NOT MET | `prompts/02-tech-lead.md` exists; `tickets/` only has a README. No scope/DoD/dependency ordering produced |
| 3 | Implementation (N>=2 workers) | PARTIAL | `enable_sub_agents: true` in the agent profile and `agent_definitions` in the API are a credible equivalent, but **untested**; no multi-file change produced |
| 4 | Testing & quality | NOT MET | `prompts/04-testing.md` exists; no tests written or run, no quality report |
| 5 | Documentation | NOT MET | `prompts/05-documentation.md` exists; `README.md` is the original 29-line project plan, not setup docs |
| 6 | Deployment validation | PARTIAL | `prompts/06-deployment.md` exists; `docker-compose.yml` + `scripts/` are real evidence but were written by hand, not by an agent |

---

## Non-Functional Requirements

### 1. Predictability & control — PARTIAL (capability present, untested)

`confirmation_policy` supports `NeverConfirm` / `ConfirmRisky` / `AlwaysConfirm`
and is exposed as `scripts/run_agent.py --confirm {never,risky,always}`.
Default is `never`, so it is currently **not** demonstrating ask-before-edit.
Needs one demo run with `--confirm always`.

### 2. Reproducibility / git — PARTIAL (capability present, untested)

- Repo is a git repo on `main`; the repo is mounted at `/opt/project` so
  agents write `docs/` and `tickets/` in place.
- `scripts/run_agent.py --worktree` sets `worktree: true`, which makes OpenHands
  create a dedicated git worktree per conversation, giving reviewable diffs.
- The stack itself is reproducible: no database, no build step, stdlib-only
  scripts, and all config is committed. A fresh clone plus `start.py` reaches
  the same state.
- Not yet demonstrated: "run the same workflow twice and get comparable
  outputs".

### 3. Context management — PARTIAL (mechanism exists, not written up)

- Artifact handoff is by design: architect writes `docs/`, tech lead reads
  `docs/` and writes `tickets/`, implementers read `tickets/`.
- The agent profile enables a condenser
  (`condenser_kind: llm_summarizing`, `max_size: 240`) to avoid silent context loss.
- Measured: a single OpenHands request is ~20.5k tokens (10.4k tool defs +
  10.1k system prompt) against a 32k context. That is the main scaling risk and
  **must be explained in the synopsis**.
- Nothing written up about behaviour as the repo grows. NOT MET as a written answer.

### 4. Security baseline — MET (after fix)

- Requirement: must not require exposing an unauthenticated model endpoint publicly.
- Both ollama instances bind `127.0.0.1` only. Verified unreachable on the LAN IP.
- LiteLLM requires the master key on `/v1/models` (401 without).
- **Fixed during this work:** `docker-compose.yml` published `4000:4000` on all
  interfaces; LiteLLM was answering on the LAN IP (health endpoint 200 without a
  key). Now `127.0.0.1:4000:4000`, verified closed.
- LLM profiles use the throwaway key in plain text rather than an encrypted
  blob, so the config is reviewable in git. Acceptable only because the proxy
  is loopback-only.
- OpenHands is `127.0.0.1:8000`.

---

## Evaluation Requirements

| Requirement | Status |
| --- | --- |
| Compare >= 2 toolchains | NOT MET — CrewAI side is entirely empty (`agents.py`, `tools.py`, `config.yaml`, `setup.md` all 0 bytes) |
| Setup complexity per toolchain | NOT MET |
| Capability coverage | NOT MET |
| Multi-endpoint support | MET for OpenHands; nothing for CrewAI |
| Failure modes | PARTIAL — real evidence gathered (below) but not written up |
| Recommendation | NOT MET |

## Required Deliverables

| Deliverable | Status |
| --- | --- |
| Synopsis, 7-10 pages | NOT MET — does not exist |
| Setup guide | PARTIAL — `scripts/` + this audit cover most of it; not written as prose |
| Demo producing arch output, a feature, tests, docs, deployment validation | NOT MET — blocked |

---

## BLOCKER: agents cannot execute tools

Reproduced 4 times, on 3 different models and 2 endpoints. The agent produces a
**correct** tool call but emits it as plain text, so OpenHands never executes it:

```json
{"name": "file_editor", "arguments": {"command": "create",
 "path": "/opt/project/artifacts/smoke-test.txt", "file_text": "OK"}}
```

Attempted: `local-tinyllama` (no tool support), `qwen2.5:3b` with native tool
calling, the same with `native_tool_calling: false` (text-parsing fallback), and
`qwen2.5-coder:7b` on endpoint B.

Ruled out by controlled test through the same proxy — each of these returns a
correct structured `tool_calls`:

- simple prompt, 1 tool
- 15 tools
- ~15k-token system prompt
- both `qwen2.5:3b` and `qwen2.5-coder:7b`

Confirmed **not** a config problem: OpenHands does send a full `tools` array
(verified in LiteLLM debug logs, `tool_choice: None`). So the tools reach the
proxy. The failure is in how this specific request/response pair is handled
between OpenHands and the local model, and needs a payload-level bisect to close.

Side finding: disabling the 66 auto-loaded skills cut prompt bloat and visibly
changed tool choice (`file_editor` -> `terminal`), so it helps, but it does not
fix execution.

The behaviour is unchanged after the setup was simplified (fewer models,
minimal plain-text profiles, `api_mode: chat`, no postgres), and the run
produced 0 `ActionEvent`s. So the cause sits in the OpenHands -> LiteLLM
response path, not in this repository's configuration.

---

## What is done and verified

- `litellm/config.yml` actually loads (the image needs an explicit `--config`).
- Two endpoints, four model aliases, role->model binding.
- Model wiring verified end to end: OpenHands -> LiteLLM -> ollama -> completion.
- `scripts/`: `start.py`, `status.py`, `run_agent.py` + `common.py` helpers
  (stdlib only, no deps). Stop and logs are plain `docker compose` commands.
- Two containers, not three: dropped the postgres service, it only existed for
  `STORE_MODEL_IN_DB`, which the file-backed config does not need.
- `SETUP.md` is the setup guide deliverable.
- Artifacts land in the repo: repo mounted at `/opt/project`, agents run with
  `working_dir=/opt/project`, so `docs/` and `tickets/` are written in place.
- Security baseline met.

## Next steps, in order

1. Fix the tool-execution blocker (highest priority; blocks every deliverable).
2. Run the six role prompts via `scripts/run_agent.py`, one per role.
3. Build the CrewAI side to zero so the comparison is real.
4. Write the synopsis and setup guide.
