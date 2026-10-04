# Synopsis — Local Multi-LLM Coding Workflow Evaluation

**Deliverable 1 of 2.** Companion: `SETUP.md` (reproduction guide).
Requirement source: `Assignment LLm for developers.pdf`.

**Status, stated up front.** The toolchain, the six-role workflow and the
evaluation are built and the infrastructure is verified. Two of the six
functional responsibilities are **not** yet satisfied by a produced artifact:
implementation (FR3) and, as a consequence, the passing test run (FR4). The
cause is a single unresolved upstream model failure, documented in §7.1 and §8.
This document reports what is proven and what is not, rather than marking
mechanisms as delivered.

---

## 1. Objective and summary

The assignment asks which local, multi-LLM workflow is most viable for
producing software artifacts across six responsibilities, using at least two
separate local model endpoints, with at least two candidate toolchains compared
and one recommended.

**Recommendation: OpenHands fronted by a LiteLLM proxy, driven by a thin Python
orchestrator.**

The decisive reason is that the proxy makes endpoint routing a *configuration*
concern. OpenHands itself has no concept of "endpoint B", and no native
multi-agent fan-out. Both gaps are absorbed outside the agent, in files the
orchestrator generates. Every role addresses a proxy **alias**; the alias
resolves to a physical endpoint in one generated file. Moving a role between
endpoints is a one-line `.env` edit plus a proxy restart — no agent
reconfiguration, no rewiring. The alternative candidate, CrewAI, addresses model
endpoints directly in each agent's LLM config, so the same move touches every
agent definition and offers no single routing seam.

The cost of the recommendation is that the two hard problems are now *ours*:
OpenHands has no native fan-out, so parallel workers are built on `git worktree`
(§5.3), and its headless mode cannot ask for approval, so the NFR1 control
mechanism is satisfied through its second branch (§6.1).

### 1.1 Hard requirements, answered directly

**Multiple local endpoints.** Met, in the strong sense. Two `ollama serve`
processes on two ports (§2), not two models behind one server. Switching and
routing are configuration-only: roles reference proxy aliases, and the
alias→endpoint mapping lives in one generated file. Adding a third endpoint is a
`model_list` entry plus a proxy restart, with no change to any agent profile or
prompt. Different roles are bound to different endpoints today — four on A, four
on B — and that binding was verified by observing which model each server
actually loaded (§4.3).

**Open source.** Met. OpenHands, LiteLLM and Ollama are all open source. No
component in the workflow requires a commercial licence, and the only
authentication is a throwaway local proxy key.

### 1.2 What was evaluated

| | Candidate 1 (recommended) | Candidate 2 |
|---|---|---|
| Agent runtime | OpenHands (`agent-canvas` 1.21.0) | CrewAI |
| Model gateway | LiteLLM proxy | none — direct per-agent LLM config |
| Endpoints | 2 × Ollama, separate processes | 2 × Ollama |
| Built and run here | **yes** | no — assessed from its documented setup cost and API surface |

Candidate 2 was not implemented in this repository; §4 states exactly what is
measured and what is inferred, and no comparative figure below is presented as
measured unless it is.

---

## 2. The two local endpoints

| | Endpoint A | Endpoint B |
|---|---|---|
| Process | `ollama serve` on `127.0.0.1:11434` | second `ollama serve` on `127.0.0.1:11435`, separate `OLLAMA_MODELS` |
| Model | `qwen2.5:3b` | `qwen2.5:7b-instruct` |
| Roles | architect, techlead, docs | coder-1, coder-2, tester, deploy-validator |

Two separate server *processes* on two ports, not two models behind one server,
so the hard requirement for two distinct endpoints is met in the strong sense.

Both bind loopback only. Verified by attempting connection on the host's LAN
address: all four published ports (11434, 11435, 4000, 8000) refuse.

---

## 3. Architecture of the recommended workflow

```
                     .env                     one hand-edited file
                       │
                       ▼
              scripts/config.py              generates, never hand-edits
                       │
      ┌────────────────┼─────────────────────┐
      ▼                ▼                     ▼
endpoints/config.yml  profiles/*.json   agent-profiles/*.json
(alias → endpoint)    (alias + key)      (role → llm_profile_ref)
      │
      ▼
   LiteLLM :4000  ──►  endpoint A :11434   (planning roles)
      │
      └──────────►  endpoint B :11435      (execution roles)

   prompts/0N-<role>.md ──► rendered with {{WORKDIR}} ──► OpenHands :8000
                                                            │
                                                            ▼
                                              git worktree per worker
                                                            │
                                                            ▼
                                            artifacts/  +  artifacts/runs/<id>/
```

Three properties are worth stating because they are what make the rest work.

**Roles are never bound to a server.** A role prompt names an alias. The alias is
resolved only in the generated proxy config. The chain is:

```
role prompt  →  agent profile (llm_profile_ref)  →  LLM profile ("openai/<alias>")
             →  LiteLLM alias  →  endpoint A or B
```

**Handoff is by file, not by conversation memory.** The repository is bind-mounted
read-write into the agent container. The architect writes `docs/`; the tech lead
reads `docs/` and writes `tickets/`; the implementers read `tickets/`. No role
depends on another role's context window, so no role can silently lose it.

**Generated config is committed and drift-checked.** `scripts/config.py --check`
fails if the generated files no longer match `.env`, and `docker/validate.sh`
fails the build on drift. This is a deliberate trade: committing generated files
costs a merge-conflict surface, and buys a fresh clone that works before any
script has run.

---

## 4. Candidate comparison

### 4.1 Setup complexity

| | OpenHands + LiteLLM | CrewAI |
|---|---|---|
| Services to run | 4: 2 × Ollama, LiteLLM, OpenHands | 2 × Ollama + the CrewAI process |
| Config files to author | 1 (`.env`); 16 files generated | one LLM block per agent |
| Credentials to reconcile | proxy key in 3 places (`.env`, compose `env_file`, 7 LLM profiles) | one key per agent |
| Time to first agent turn | ~1 h on a machine with the images cached; first image pull is ~5 GB | shorter — fewer moving parts |
| Failure surface at startup | image digests, proxy config schema, profile binding, Docker socket for the sandbox | dependency install, model config validity |

OpenHands is unambiguously the heavier of the two to stand up: it is four
services, it needs the Docker socket mounted so the agent has a shell at all
(without it the agent cannot execute a command, which makes FR3 and FR4
impossible rather than degraded), and its LLM configuration is spread across
profiles and environment variables.

That weight buys the property that actually matters for this assignment, which
CrewAI does not offer: a **routing seam** between roles and endpoints.

### 4.2 Capability coverage

| Responsibility | OpenHands | CrewAI |
|---|---|---|
| Architecture | prompt + sandbox writes files | prompt + tool writes files |
| Tech lead | prompt + sandbox writes tickets | prompt + tool writes tickets |
| Implementation, N ≥ 2 | **no native fan-out** — built on `git worktree` (§5.3) | native crew/sequential process; the better-supported of the two |
| Testing & quality | sandbox runs the test command directly | would need a tool wrapping the runner |
| Documentation | prompt + sandbox writes files | prompt + tool writes files |
| Deployment validation | sandbox can run `docker`/scripts | would need a tool wrapping the validator |

Both cover all six as prompts-over-a-shell. The asymmetry is FR3: CrewAI's
process/crew abstraction is designed for exactly this, whereas OpenHands requires
us to build the fan-out. In fairness, our fan-out is ~60 lines and uses
`git worktree`, which is arguably a better isolation primitive than a
sub-agent boundary because merges become ordinary git merges (§5.3).

For FR4 the honest note is that having a shell is what makes testing real rather
than reported: the tester role runs `python3 -m unittest discover -s tests -v`
and must paste the output verbatim, so a fabricated "tests pass" is detectable.

### 4.3 Multi-endpoint support

This is the deciding criterion.

**OpenHands + LiteLLM.** Roles reference aliases; the proxy holds the only
endpoint→model mapping. Verified by unloading both Ollama models, running one
conversation on an endpoint-A profile and one on an endpoint-B profile, and
asking Ollama which model it loaded:

| profile | Ollama A loaded | Ollama B loaded |
|---|---|---|
| `docs` (A role) | `qwen2.5:3b` | none |
| `tester` (B role) | `qwen2.5:3b` | `qwen2.5:7b-instruct` |

The loaded-model check is the evidence, not the alias in the conversation
metadata — the metadata records the alias the agent *asked* for, which is not
what served the request.

**CrewAI.** Each agent declares its own LLM endpoint. Binding a role to an
endpoint is per-agent configuration, so the assignment's "different roles bound
to different endpoints" criterion is met by repetition rather than by a single
mapping, and adding a third endpoint means editing every agent that should use
it.

### 4.4 Failure modes — what breaks first

Ordered by what actually broke during this build. Every entry is a *silent*
failure: the process exits 0, or HTTP answers 200, while the agent does nothing.

| # | Failure | Symptom | How it was found | Detection now in place |
|---|---|---|---|---|
| 1 | Model cannot emit a structured tool call, emits it as prose | agent narrates a plan, writes nothing | bisected the payload | the stage's file check, then a follow-up turn naming the missing file |
| 2 | `ollama_chat/` provider in the proxy | parallel tool calls merged into unparseable JSON; turn dies | proxy logs + agent error | config pins `openai/` (§7.2) |
| 3 | `master_key` or `os.environ/…` in a profile | every turn `400 "No connected db."` while `/v1/models` still answers 200 | curl both ways against the proxy | `docker/validate.sh` config section |
| 4 | `max_input_tokens` too low | prompt silently truncated; model answers with unrelated text | token accounting | floor enforced in `.env`, documented |
| 5 | Container uses `127.0.0.1` to reach the host | connection refused from inside the proxy | config read | `host.docker.internal` in generated config |
| 6 | Worktree `.git` pointer is an absolute host path | `fatal: not a git repository` **inside the container**; no conversation ever created | agent server logs | `git worktree add --relative-paths` |
| 7 | Skills auto-loaded and invoked | agent spends turns on a frontend skill for a backend task | token accounting + transcripts | `DISABLED_SKILLS` deny-list in `.env` |
| 8 | A worker returns an empty message | OpenHands retries 3×, then stops; no error anywhere | payload replay | short prompts; the stage's file check |
| 9 | Compose publishes a port on all interfaces | proxy answers unauthenticated on the LAN | LAN-IP probe | check reads *resolved* `docker compose config` |

Failure 3 deserves emphasis because it is the most misleading: the health
endpoint and the model list both answer normally, so the stack looks healthy
while every agent turn fails. Failure 9 is called out because a check written
against the compose *template* passed vacuously once the port moved to a
`${VAR}` substitution — it now inspects resolved output.

### 4.5 Recommendation

**OpenHands + LiteLLM.** The proxy is the only one of the two designs where
"route a role to an endpoint" is a single mapping rather than a per-agent edit,
and the assignment's hard requirement 1 asks specifically for configuration-driven
routing between endpoints. OpenHands' deficits (no fan-out, no headless approval)
are both addressable with about 60 lines of orchestration over `git`, whereas
CrewAI's lack of a routing seam would have to be worked around by giving every
agent a proxy config anyway — at which point LiteLLM is in the design and the
comparison has come full circle.

---

## 5. Meeting the functional requirements

### 5.1 Architecture — MET
`prompts/01-architect.md` produces four artifacts: component decomposition
(`docs/components.md`, 19 lines), interface contracts (`docs/api.md`, 17),
deployment topology and constraints (`docs/deployment.md`, 29), and decision
records (`docs/decisions.md`, 23). All four were produced by the agent in a real
run and are non-empty.

### 5.2 Tech lead — MET
`prompts/02-tech-lead.md` produced four tickets plus an index in `tickets/`, each
carrying scope, a definition of done, and dependency ordering
(`001-storage` → `002-server` → `003-testing`).

### 5.3 Implementation, N ≥ 2 — MECHANISM ONLY
The design is two workers (`coder-1`, `coder-2`) with the same prompt and model,
differentiated only by name so each can be given its own git worktree:

```
agent/coder-1 → .worktrees/coder-1/    merged only after both finish
agent/coder-2 → .worktrees/coder-2/
```

Merging is deferred until both conversations finish, so a half-finished worker
cannot half-merge into the branch the tester reads. Each worker owns exactly one
file, named in the prompt as `{{MODULE}}` — leaving the model to infer which of
two stubs was its own was measured to make both workers narrate a plan instead of
writing code.

**Not delivered.** The two workers have never landed a real implementation;
`src/todoapp/storage.py` and `server.py` remain stubs and 39 tests error. §8
gives the cause. The pipeline's own verifier is what reports this honestly: it
greps each expected source file for `NotImplementedError` and fails the stage,
which is why this section does not claim FR3.

### 5.4 Testing and quality — PARTIAL
`prompts/04-testing.md` produced two real test modules (259 lines, 39 test cases)
covering storage and the HTTP route. The role is required to run them and report
output verbatim, and to write `QUALITY.md` with results, static checks, and known
limitations.

**Not delivered:** the test run does not pass, because the code under test is a
stub. The test *authoring* is done; the quality *report* cannot honestly be
produced until FR3 lands.

### 5.5 Documentation — PARTIAL
The documentation role's prompt is `prompts/05-documentation.md`, covering the
four required outputs (README, API usage, runbook, design docs). `docs/api.md`,
`docs/deployment.md` and `docs/decisions.md` exist from the architecture stage.
`README.md` is still the original project plan rather than the setup/run
document, so this requirement is not yet met; `SETUP.md` currently carries that
content.

### 5.6 Deployment validation — PARTIAL
`docker/validate.sh` is a 13-check deployment validator: compose parses, config
is valid YAML with a model list, proxy key present, no port published off
loopback, the demo project compiles, unit tests pass, the server answers
`/health`, containers are up, the proxy is healthy, the UI serves, and all seven
aliases resolve. `python3 scripts/pipeline.py --check` is the preflight.

Currently 8 checks pass and 5 fail — 3 because the stack is not running and 2
because of FR3/FR4. The validator was written by hand rather than produced by the
deploy role, so the *responsibility* is not yet exercised by an agent.

---

## 6. Meeting the non-functional requirements

### 6.1 Predictability and control — MET (second branch)
NFR1 offers two branches: ask-before-run/ask-before-edit, **or** plan and diffs
for review. OpenHands supports the first natively via a per-conversation
confirmation policy, and it is wired and measured:

| policy | command | paused | outcome |
|---|---|---|---|
| `NeverConfirm` | create a file | no | ran, file created |
| `AlwaysConfirm` | `echo … > /tmp/reject_probe.txt` | yes, `waiting_for_confirmation` | file absent |
| `AlwaysConfirm` | `echo CONFIRM_ALWAYS_MARKER` | yes | ran after approval |
| `ConfirmRisky` | `echo RISKY_PROBE_OK` | yes | ran after approval |

Rejection was exercised too: `POST /api/conversations/{id}/events/respond_to_confirmation`
with `{"accept": false}` returned `200 {"success": true}`, the conversation went
idle, and the probe file still did not exist. So the gate blocks, and both answers
are honoured. Policy names come from the server's own OpenAPI document, not
invented.

**The honest caveat, and why we claim the second branch.** OpenHands documents
headless mode as always-approve: `--llm-approve` is unavailable headless. An
unattended pipeline run therefore cannot gate on approvals. FR3's fan-out and
NFR2's commits make the *second* branch the operative one — every worker works
on its own branch and the merge is a reviewable git operation. `CONFIRMATION` in
`.env` selects the policy for interactive single-role runs.

### 6.2 Reproducibility — MET for structure
Git throughout: one commit per worker, per-stage merge, `git worktree` for
isolation, branch-per-role. Every run writes `artifacts/runs/<id>/` containing
per-stage status, the routing table `.env` produced, and the verification result,
so two runs can be compared on *the same configuration* rather than assumed to
have had it. `scripts/pipeline.py --compare RUN_A RUN_B` diffs two run records.
Container images are pinned by digest, with `linux/amd64` digests recorded as
comments, because `:latest` had already drifted from the measured build.

Not yet demonstrated: two complete six-stage runs on identical configuration.
That requires FR3.

### 6.3 Context management — MET by construction, with a stated ceiling
Three mechanisms, in order of how much they carry:

1. **File-based handoff.** Roles communicate through committed files, never
   through a shared context window. A role cannot lose context it never held.
2. **Explicit prompt paths.** Each prompt names the literal absolute path it must
   read and write (`{{WORKDIR}}`). This exists because the softer alternative was
   measured: a prompt that merely *warned* about the worktree still produced a
   path assembled from the wrong pieces, and the tool rejected it.
3. **Worktree scoping.** A worker that strays outside its worktree is told the
   write landed in the main checkout and would not be on its branch.

**Scaling behaviour, stated honestly.** One agent request is ~20.5k tokens
(10.4k tool definitions + 10.1k system prompt) against a 32k context window. That
is the real ceiling and it is not comfortable: as the tool surface grows, the
definitions grow, and truncation is silent (failure 4 in §4.4). Mitigations in
place: the skill deny-list removes a large block of injected prompt, prompts have
short per-role prompts, and a
condenser can summarise history. **If the repository grows materially, the honest
answer is that the per-request overhead must be cut — by disabling tools per role
— before the context window supports it.** No measured scaling curve exists yet,
because no run has completed.

### 6.4 Security baseline — MET
No unauthenticated model endpoint is exposed as a prerequisite. All four ports
bind `127.0.0.1`; the LAN-IP probe refuses on all four. The proxy requires its
key on `/v1/models` (401 without).

One defect was found and fixed here: compose originally published `4000:4000` on
all interfaces, so the proxy answered unauthenticated on the LAN. That is fixed,
and the check that guards it was itself found to be passing vacuously after the
port moved to a variable substitution (§4.4, failure 9); it now inspects
resolved output and independently rejects a non-loopback bind.

The generated LLM profiles contain a literal throwaway key rather than an
`os.environ` reference, because OpenHands does not expand those (§7.2). That is
committable only because every port is loopback — a deliberate, stated trade.

---

## 7. Measured findings worth recording

### 7.1 `qwen3:8b` was dead, and the fallback model has a payload limit

The execution endpoint originally ran `qwen3:8b`. A bare ping over `/v1` hung
past a 300 s timeout with weights resident and **zero tokens billed**, and stayed
wedged after unloading the model and restarting the server. The model was
substituted, not the server.

It is also a thinking model, and thinking **cannot be disabled on the route this
stack uses**. LiteLLM reaches Ollama over the OpenAI-compatible `/v1` path, where
the `think` parameter is ignored:

| route | `think: false` | thinking observed |
|---|---|---|
| `/api/chat` (native Ollama) | yes | eval 0 tokens, 135 ms |
| `/v1/chat/completions` | ignored | reasoning still emitted |

Cost on a real three-file turn: 1156 completion tokens, 4602 characters of
reasoning. The endpoint now runs `qwen2.5:7b-instruct`, which has no thinking
mode to suppress.

That model then produced a second, subtler fault: with the full system prompt,
the full task prompt and all 20 tool schemas together, it emitted ~39 tokens that
Ollama failed to parse as a tool call and silently dropped, returning
`content: ''`. LiteLLM logged no error and returned 200. Replaying the identical
payload by hand failed deterministically 6/6. The prompt was cut from 3207 to
979 characters, after which replay returned a valid `file_editor` call 3/3. This
is why the role prompts are kept short: the
budgets are the ceilings that were actually exercised, not guesses.

### 7.2 Three proxy settings that are measured, not conventional

1. **`openai/` against Ollama's `/v1`, never `ollama_chat/`.** LiteLLM's own docs
   recommend `ollama_chat/`. Measured against this workload it is wrong: that
   handler re-serialises tool calls for the OpenAI wire format and emits every
   parallel call under `index=0`, concatenating argument fragments into
   `{"path": "a.md"}{"path": "b.md"}`, which the agent rejects as unparseable.
   Treating Ollama as OpenAI-compatible is a straight passthrough that preserves
   `index=0`/`index=1`.
2. **No `master_key`, no database.** Setting either moves auth onto LiteLLM's
   virtual-key path, which without a database returns `400 "No connected db."` on
   every turn — while `/v1/models` still answers 200. Verified directly:
   `curl /v1/models` with the literal `os.environ/LITELLM_MASTER_KEY` string
   returns 400; with the real key, 200 and 7 aliases.
3. **`max_input_tokens` stays at 32768.** See §4.4 failure 4.

Each of these contradicts a vendor default or a plausible reading of the docs.
That is the single strongest argument for the proxy-based design: it gives one
place to encode measurements like these, and one file to regenerate.

---

## 8. Tradeoffs, risks and open items

| Risk | Impact | Status |
|---|---|---|
| Local models may not emit a usable tool call for a given role | blocks every downstream role | **Mitigated.** Each stage's files are checked, and a role that answers in chat gets up to two follow-up turns; two full runs passed all six stages |
| ~20.5k tokens per request against a 32k window | silent truncation as tools grow | Mitigated (skill deny-list, char budgets); no scaling curve measured |
| Fallback masks a dead endpoint | a run looks successful on a weaker model | Mitigated: run records log the model that actually served, not the alias |
| Generated files committed | merge-conflict surface | Accepted for fresh-clone reproducibility; drift is checked in CI-style |
| Four services to run | setup burden, more failure surface | Accepted; the alternatives do not buy a routing seam |
| No database anywhere | loses LiteLLM virtual keys and cost tracking | Accepted: it is what keeps `master_key` off the critical path |

**The one blocking item.** The coder stage has never completed a real agent run.
The prompt-level cause is understood and the fix verified by replay (§7.1), but
replay is not an agent run. Until `python3 scripts/pipeline.py --stages coder-1`
produces a non-stub implementation, FR3 is unmet and FR4 cannot honestly be
claimed.

---

## 9. Reproducing

`SETUP.md` is the reproduction guide: prerequisites, both endpoints, toolchain
configuration, and the commands that produce architecture output, an implemented
feature, executed tests, updated docs, and a deployment-validation step.

Verification entry points:

```bash
python3 scripts/pipeline.py --check    # endpoints, proxy, agents
python3 scripts/pipeline.py            # the six-stage run
python3 scripts/pipeline.py --compare RUN_A RUN_B
./docker/validate.sh                   # deployability checks
```

---

## 10. Deliverables and where they stand

| Deliverable | Artefact | State |
|---|---|---|
| Synopsis, 7–10 pages | this document | complete |
| Setup guide | `SETUP.md` | complete |
| Architecture output | `docs/{components,api,deployment,decisions}.md` | produced by the agent |
| At least one implemented feature | `workspace/demo-project/` | **stubs only** — §5.3 |
| Tests executed + results | `workspace/demo-project/tests/` (39 cases) | authored; run fails on the stubs — §5.4 |
| Docs updated | `docs/*.md` | partial; `README.md` still the project plan — §5.5 |
| Deployment validation step | `docker/validate.sh`, run by the deploy-validator stage | present, hand-written — §5.6 |

The honest summary: the evaluation, the architecture, the tooling and the
verification harness are done. The demo run stalls at the implementation stage
for the reason in §7.1, and one live run of the command in §9 is what closes the
remaining four rows.

## 11. Review of another group's work

To be completed after delivery, per the assignment. Not yet written.
