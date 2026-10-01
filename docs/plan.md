# OpenHands + LiteLLM Implementation Plan

> ## STALE — DO NOT ACT ON THIS DOCUMENT
>
> Written 2026-09-28 against an earlier repo state. Several of its central claims
> are **wrong** and have been disproven by later work:
>
> - §1.1 claims `ghcr.io/openhands/agent-canvas` is not a published image. It is
>   published, pulls fine (5.2 GB), and is what `docker-compose.yml` uses.
> - §1.1 claims the app listens on `:3000`. The running stack serves on `:8000`.
> - §1.2 describes a legacy V0 `config.toml` layout the repo no longer uses.
> - §2's "BLOCKED: agents cannot execute tools" is **resolved**. `SETUP.md`
>   documents the four wiring faults that caused it; agents now execute tools.
> - §2 lists `workspace/demo-project/` as README-only — still true.
>
> Live sources of truth: `SETUP.md` (what the stack is and how to run it),
> `docs/requirements-audit.md` (requirement-by-requirement status),
> `docs/functional-requirements.md` (how each responsibility is met).
> Kept only for its risk table (§4) and phasing ideas (§3), which remain sound.

Plan to make the recommended toolchain satisfy the assignment's hard and
functional requirements. Derived from an audit of the current repo state
against the current OpenHands and LiteLLM releases.

Read this together with `README.md` (toolchains, endpoints, team, timeline).

---

## 1. Status: the repo is a skeleton targeting a version that no longer exists

Three findings block the current setup outright.

### 1.1 The OpenHands image in `docker-compose.yml` does not exist

`ghcr.io/openhands/agent-canvas` is not a published image. The `ghcr.io/openhands/*`
organisation is the **agent-server** (the sandbox), not the application.

| | Current repo | Correct |
| --- | --- | --- |
| App image | `ghcr.io/openhands/agent-canvas` | `docker.openhands.dev/openhands/openhands:1.8` |
| App port | `8000` | `3000` |
| Sandbox image | (none) | `ghcr.io/openhands/agent-server:<version>-python` |

### 1.2 `openhands/config.toml` is legacy V0 and is never read

`openhands/core/config/llm_config.py` on `main` is marked:

> IMPORTANT: LEGACY V0 CODE - Deprecated since version 1.0.0, scheduled for removal
> April 1, 2026

V1 reads LLM configuration from `~/.openhands/agent_settings.json` with keys
`llm.model` / `llm.api_key` / `llm.base_url`, or from the environment variables
`LLM_MODEL` / `LLM_API_KEY` / `LLM_BASE_URL` when launched with
`--override-with-envs`. The file mounted at `/root/.openhands/config.toml`
has no effect.

### 1.3 No Docker socket means no sandbox at all

V1 starts the agent-server sandbox as a **sibling container launched through the
Docker socket**. Without `-v /var/run/docker.sock:/var/run/docker.sock` the agent
has no shell. This is not a degradation — it makes functional requirement 3
(multi-file changes) and functional requirement 4 (create and run tests)
impossible.

---

## 2. Gap analysis

| Area | Current state | Blocking issue |
| --- | --- | --- |
| Compose image / port | `agent-canvas` on `:8000` | Wrong image, wrong port |
| Compose sandbox | No docker.sock, no `AGENT_SERVER_*`, no `SANDBOX_VOLUMES` | No command execution, repo invisible to agent |
| OpenHands model name | `model = "architecture-model"` | Must be `litellm_proxy/architecture-model`; a bare name carries no provider prefix so LiteLLM cannot route it |
| OpenHands auth | `api_key = "local-llm"` | Does not match `LITELLM_MASTER_KEY=sk-local-not-secure`; results in 401 |
| LiteLLM Ollama entry | `localhost:11434/api`, `ollama/tinyllama` | `localhost` resolves to the LiteLLM container itself, not the host. Must be `host.docker.internal`. The `/api` suffix is wrong. `ollama/` targets the generate endpoint, not chat |
| LiteLLM second entry | `qwen3.6:35b-a3b` | Model does not exist |
| LiteLLM routing | Two different `model_name`s, no `router_settings` | **Hard requirement 1 unmet**: no model group, no failover, no retries |
| Model capability | `tinyllama` | Too weak for reliable tool calling; will fail on the first real task |
| Role prompt discovery | `prompts/*.md` at repo root | OpenHands auto-loads only `.openhands/skills/` (V1) or `.openhands/microagents/` (V0). No `.openhands/` directory exists, so **no prompt is ever loaded** |
| Prompts 03 / 04 | Truncated at `## Output Format` | Incomplete, and structurally inconsistent with 05 / 06 |
| Role → endpoint binding | "You run on the reasoning model (Endpoint A)" as prose | Nothing mechanically binds a model to a role |
| N ≥ 2 workers (FR 3) | Requested in `prompts/03-implementation.md` | OpenHands has no native fan-out. Needs N instances on separate git worktrees |
| Testing (FR 4) | `workspace/demo-project/` is a README only | No code, no test runner, no linter. Nothing to test or lint |
| Deployment validation (FR 6) | None | Root `docker-compose.yml` is the *toolchain*, not the *artefact under test*. Demo project needs its own |
| Artefacts | `./artifacts` mounted in compose, directory absent | No run evidence for the "run twice and compare" requirement |
| `.env.example` | `OLAMA_SECRET`, `OTHERLLM` | Dead variables, referenced by no config |
| Version pinning | `:latest` everywhere | Not reproducible |

### The design conflict to resolve first

The OpenHands documentation states that headless mode:

> Headless mode always runs in `always-approve` mode. The agent will execute all
> actions without any confirmation. This cannot be changed—`--llm-approve` is not
> available in headless mode.

Meanwhile `prompts/01-architect.md` instructs:

> Always show me what you want to write/change before saving it. I need to say
> "ok" first.

These are incompatible. Headless automation therefore cannot satisfy the
"ask-before-run / ask-before-edit" branch of non-functional requirement 1. Three
viable resolutions:

1. Drive the **interactive** CLI (no `--headless`) and supply confirmations from
   outside the agent.
2. Satisfy NFR 1 through its **second** branch instead: *plan + diffs for review
   before execution*.
3. Use `--llm-approve` in interactive mode to route confirmation through the
   security analyzer.

Pick one deliberately and justify it. This is a strong candidate for the
"failure modes" section of the synopsis.

---

## 3. Plan

### Phase 1 — Fix the LLM gateway (no OpenHands yet)

- [x] **1.1** Create `.env` from `.env.example`. Remove the dead
      `OLAMA_SECRET` / `OTHERLLM` entries. Set a real `LITELLM_MASTER_KEY`.
- [x] **1.2** Rewrite `litellm/config.yml`:
      - Use `host.docker.internal` for **both** upstreams, never `localhost`.
      - Ollama entry: `ollama_chat/<model>` (chat endpoint, not generate),
        `api_base` **without** a trailing `/api`, and
        `model_info.supports_function_calling: true`.
      - Second endpoint: `openai/<model>` with `api_base` ending in `/v1`.
- [ ] **1.3** Define **one alias per role** — `architect`, `tech-lead`, `coder`,
      `tester`, `docwriter`, `deployer` — so that roles bind to endpoints through
      configuration rather than by rewiring. This is what hard requirement 1 and
      the "different roles bound to different endpoints" evaluation criterion ask
      for.
- [ ] **1.4** Add a **shared `model_name` group** spanning both endpoints, plus
      `router_settings` (`routing_strategy`, `num_retries`, `fallbacks`) and
      `general_settings: store_model_in_db: false`. This is what makes routing and
      switching configuration-driven and survives one endpoint going down.
- [ ] **1.5** Verify the gateway in isolation:
      - `curl localhost:4000/health/liveliness`
      - `curl localhost:4000/v1/models`
      - A tool-calling round trip against each role alias.
      - Stop one endpoint mid-request and confirm failover, not a hard failure.

**Exit criteria:** every role alias answers a tool-call request; killing one
upstream does not break the proxy.

### Phase 2 — Fix OpenHands

- [ ] **2.1** Replace `openhands/config.toml` with an `agent_settings.json`
      (or drop the file and drive everything through env vars +
      `--override-with-envs`). `model` must be `litellm_proxy/<alias>`,
      `base_url` must be `http://litellm:4000` with **no** `/v1` suffix, and
      `api_key` must equal `LITELLM_MASTER_KEY`.
- [ ] **2.2** Correct `docker-compose.yml`: real app image, port `3000`,
      the Docker socket mount, `AGENT_SERVER_IMAGE_REPOSITORY` +
      `AGENT_SERVER_IMAGE_TAG`, `SANDBOX_VOLUMES` for the demo repo, and
      `extra_hosts` for **both** the app and sandbox containers. Add a healthcheck
      and a `depends_on: service_healthy` gate so the app does not start before
      the gateway is up.
- [ ] **2.3** Smoke test one real task end to end: create a file, run a command,
      read the output. This is the proof that the sandbox works.

**Exit criteria:** OpenHands completes a file-write and a shell-command task
against the local gateway.

### Phase 3 — Roles and prompts

- [ ] **3.1** Move the role prompts into the demo repository under
      `.openhands/skills/<role>.md` with YAML frontmatter so OpenHands
      auto-discovers them. Keep `prompts/` as the authoring source or delete it
      to avoid two competing copies.
- [ ] **3.2** Add `.openhands/skills/repo.md` carrying shared conventions and the
      run instructions.
- [ ] **3.3** Finish `prompts/03-implementation.md` and `prompts/04-testing.md` —
      both currently stop at `## Output Format` — and align all six prompts on one
      structure.
- [ ] **3.4** Replace the "You run on the reasoning model (Endpoint A)" prose with
      a mechanical binding: each role is launched with its own
      `litellm_proxy/<alias>`.
- [ ] **3.5** Create the target directories and scaffolds: `docs/components.md`,
      `docs/api.md`, `docs/deployment.md`, `docs/decisions.md`,
      `docs/handoff.md`, `docs/questions.md`, and a `tickets/` directory, so the
      handoff contract in the prompts has somewhere to land.

### Phase 4 — Demo project

- [ ] **4.1** Build a small but real package in `workspace/demo-project/`: source
      files, a `tests/` directory, and configured `pytest`, `ruff` and `mypy`.
- [ ] **4.2** Include one deliberately failing test so the testing role has
      something to discover and fix.
- [ ] **4.3** Give the demo project its own `Dockerfile` / `docker-compose.yml`
      and an env-var reference, satisfying the deployment-validation
      responsibility.

**Exit criteria:** `pytest` and `ruff` run locally in the demo project, and the
project can be container-built.

### Phase 5 — Orchestration

- [ ] **5.1** Fan out with `git worktree` per worker: N independent OpenHands
      conversations, each on its own branch, each bound to a different
      `litellm_proxy/<alias>`. This is the "credible equivalent design" that
      satisfies FR 3, and it simultaneously produces the reviewable diffs that
      NFR 2 asks for.
- [ ] **5.2** Script the queue: launch workers, capture `--json` JSONL per worker,
      gate on exit code, and emit a merge proposal for review.
- [ ] **5.3** Resolve the approval conflict from section 2 and document the
      decision plus its consequences.

### Phase 6 — Evidence and reproducibility

- [ ] **6.1** Create `artifacts/runs/<timestamp>/` and capture per-role logs,
      diffs, and test output.
- [ ] **6.2** Run the full workflow **twice** and compare structure. This is the
      explicit NFR 2 deliverable and also produces the raw material for the
      synopsis.
- [ ] **6.3** Pin image tags and model versions everywhere, so the third-party
      setup guide is reproducible.
- [ ] **6.4** Write the setup guide so a third party can go from a clean machine to
      a working demo workflow: prerequisites, both endpoints, toolchain config,
      and a run that produces architecture output, one implemented feature,
      executed tests, updated docs, and a deployment-validation step.

---

## 4. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| **Local model tool-calling reliability.** OpenHands depends on dependable native function calling. Small local models tend to loop, emit malformed tool arguments, or ignore schema constraints | Blocks everything downstream | Validate tool calling in step 1.5 **before** building any orchestration. If it fails, change the model choice or the design, not the pipeline |
| Gateway hostname confusion (`localhost` vs `host.docker.internal`) | Silent connection refused from inside containers | Phase 1.2; assert explicitly in the health check |
| Headless always-approve vs NFR 1 | Requirement not met as currently designed | Decide in step 5.3 and document |
| No native multi-agent support in OpenHands | FR 3 depends entirely on custom glue | Phase 5.1 worktrees; budget the time, it is the largest custom component |
| Pinning `latest` images | Breaks between two runs, destroying the reproducibility comparison | Phase 6.3 |

## 5. Suggested order

Phases 1 and 2 are strictly sequential and are the gate for everything else:
validate tool calling first, then prove the sandbox. Phases 3 and 4 can overlap
once Phase 2 exits. Phase 5 depends on Phase 3 (prompts must be discoverable) and
Phase 4 (workers need real code to change). Phase 6 needs the whole pipeline to
exist.
