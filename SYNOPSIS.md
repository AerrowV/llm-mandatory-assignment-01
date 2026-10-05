# Synopsis — Local Multi-LLM Coding Workflow Evaluation

**Deliverable 1 of 2.** Companion: `SETUP.md` (reproduction guide).
Requirement source: `Assignment LLm for developers.pdf`.

**Status, stated up front.** The toolchain and the six-role workflow are built
and run end to end: every stage delivers its files in one unattended run
(`artifacts/runs/20261005T085117Z`). The demo is a small command-line
calculator; in the latest run the two coders' code passes 10 of its 11 tests
(`artifacts/runs/20261005T091026Z`). What the small local models do *not* yet
do reliably is improve their code in a fix round (§8). This document reports
what is proven and what is not, rather than marking mechanisms as delivered.

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
prompt. Different roles are bound to different endpoints today — five on A, the two
coders on B — and that binding was verified by observing which model each server
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
| Model | `qwen2.5:3b` | `llama3.1:8b` |
| Roles | architect, techlead, tester, docs, deploy-validator | coder-1, coder-2 |

Endpoint B serves only the coders, so the two run in parallel on it
(`OLLAMA_NUM_PARALLEL=2`) without queueing behind another role. Their sampling
temperature is `CODER_TEMPERATURE` in `.env`, 0 by default: at 0.3
`llama3.1:8b` starts describing tool calls in text instead of making them.

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
   LiteLLM :4000  ──►  endpoint A :11434   (architect, techlead, tester, docs, deploy)
      │
      └──────────►  endpoint B :11435      (coder-1, coder-2)

   prompts/0N-<role>.md ──► rendered with {{WORKDIR}} ──► OpenHands :8000
                                                            │
                                                            ▼
                                              git worktree per worker
                                                            │
                                                            ▼
                                                  artifacts/runs/<id>/
```

Three properties are worth stating because they are what make the rest work.

**Roles are never bound to a server.** A role prompt names an alias. The alias is
resolved only in the generated proxy config. The chain is:

```
role prompt  →  agent profile (llm_profile_ref)  →  LLM profile ("openai/<alias>")
             →  LiteLLM alias  →  endpoint A or B
```

**Handoff is by file, plus a short team chat.** The repository is bind-mounted
read-write into the agent container. The architect writes `docs/`; the tech lead
reads `docs/` and writes `tickets/`; the coders read `TASK.md`. No role depends
on another role's context window. Each role's final reply (cut to 300
characters) is also posted to a team chat, and the last four messages are
appended to every later prompt, so a role sees what its teammates reported.

**The harness runs the tests, the agents report on them.** After the tester
stage the pipeline runs the unit tests on the host. If any fail, each coder
gets only the failures in its own module (a fix round, at most two), its
previous attempt as `<module>.prev`, and the spec. A rewritten module is kept
only if it raises the number of passing tests; otherwise the previous code is
restored and the team chat says so. The tester and deploy-validator receive the
real test and `docker/validate.sh` output in their prompt instead of running
the commands themselves.

**Generated config is committed and regenerated on every run.**
`scripts/config.py` rewrites `endpoints/config.yml` and the 14 profiles from
`.env` at the start of every pipeline run, and restarts LiteLLM when the routing
changed. Committing them costs a merge-conflict surface and buys a fresh clone
that works before any script has run.

---

## 4. Candidate comparison

### 4.1 Setup complexity

| | OpenHands + LiteLLM | CrewAI |
|---|---|---|
| Services to run | 4: 2 × Ollama, LiteLLM, OpenHands | 2 × Ollama + the CrewAI process |
| Config files to author | 1 (`.env`); 15 files generated | one LLM block per agent |
| Credentials to reconcile | proxy key in 3 places (`.env`, compose `env_file`, 7 LLM profiles) | one key per agent |
| Time to first agent turn | ~1 h on a machine with the images cached; first image pull is ~5 GB | shorter — fewer moving parts |
| Failure surface at startup | image digests, proxy config schema, profile binding, repository mount for the agent's shell | dependency install, model config validity |

OpenHands is unambiguously the heavier of the two to stand up: it is four
services, the repository must be mounted into the agent container so the agent
has a shell on the project (without it the agent cannot write or run anything,
which makes FR3 and FR4 impossible rather than degraded), and its LLM
configuration is spread across profiles and environment variables.

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

(Measured with the earlier routing, when the tester ran on B with
`qwen2.5:7b-instruct`; the method is the same for the current routing.)

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

Evidence for every row: `artifacts/runs/20261005T085117Z` (all six stages in one
run) and `artifacts/runs/20261005T091026Z` (coders onward, after the spec was
made clearer). `python3 scripts/demo.py --show` prints both the record and the
produced files.

### 5.1 Architecture — MET
`prompts/01-architect.md` produces five files: component decomposition
(`docs/components.md`), interface contracts (`docs/api.md`), deployment topology
(`docs/deployment.md`), decision records (`docs/decisions.md`) and the handoff
to the tech lead (`docs/handoff.md`). The pipeline checks that each exists and
is non-trivial. They are short — `qwen2.5:3b` writes thin documents — but they
are about this repository, not a generic system.

### 5.2 Tech lead — MET
`prompts/02-tech-lead.md` produces the index `tickets/list.md` and three tickets,
`001-ops` → `002-cli` → `003-testing`, each with scope, acceptance criteria and
dependencies.

### 5.3 Implementation, N ≥ 2 — MET
Two workers (`coder-1`, `coder-2`) share one prompt and model and run in
parallel, each in its own git worktree on its own branch:

```
agent/coder-1 → .worktrees/coder-1/   writes src/calc/ops.py
agent/coder-2 → .worktrees/coder-2/   writes src/calc/cli.py
```

Each worker owns exactly one module, named in the prompt as `{{MODULE}}` —
leaving the model to infer which of two stubs was its own was measured to make
both workers narrate a plan instead of writing code. After both finish, the
harness commits each branch and takes only that worker's module into the main
checkout, so one worker cannot overwrite the other's file. A module that still
contains `NotImplementedError` fails the stage.

### 5.4 Testing and quality — MET, with one failing test
The spec ships 11 unit tests (`workspace/demo-project/tests/`). The harness runs
them and `python3 -m compileall` on the host; the tester reads the real output
and the code and writes `workspace/demo-project/QUALITY.md` with test results,
static checks and known limitations. In the latest run 10 of 11 pass; the
failure is real (`run.py add 2 3` prints `5.0`, the spec says `5`) and is
reported as such. Failing tests trigger the fix rounds described in §3.

### 5.5 Documentation — MET
`prompts/05-documentation.md` makes the docs role write
`workspace/demo-project/README.md` with setup, usage, runbook (exit codes) and
troubleshooting sections, based on `TASK.md`, `run.py` and `QUALITY.md`; the
pipeline checks all four sections are present. Design documentation is the
architect's `docs/`. The repository's own setup guide (`SETUP.md`) is hand-written.

### 5.6 Deployment validation — MET
`docker/validate.sh` is a 9-check deployment validator: compose parses, the
proxy key is set, the generated config lists all 7 roles, every published port
is bound to 127.0.0.1, the demo modules compile, its unit tests pass, the CLI
runs, the proxy is healthy and OpenHands answers. The harness runs it, and the
deploy-validator writes `docs/deployment-validation.md` (method, checklist,
verdict, risks) from the real output. The script is hand-written; the agent's
part is reading and reporting it, not inventing results.

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

Not yet demonstrated: two complete six-stage runs on identical configuration
compared with `--compare`. The kept records are one full run and one run from
the coders onward; older debug runs were removed and remain in git history.

### 6.3 Context management — MET by construction, with a stated ceiling
Three mechanisms, in order of how much they carry:

1. **File-based handoff.** Roles communicate through committed files, never
   through a shared context window. A role cannot lose context it never held.
2. **Explicit prompt paths.** Each prompt names the literal absolute path it must
   read and write (`{{WORKDIR}}`). This exists because the softer alternative was
   measured: a prompt that merely *warned* about the worktree still produced a
   path assembled from the wrong pieces, and the tool rejected it.
3. **Worktree scoping.** Each coder's working directory is its own worktree,
   and only its own module is taken back into the main checkout.

**Scaling behaviour, stated honestly.** With OpenHands' default tool set one
agent request was ~20.5k tokens (10.4k tool definitions + 10.1k system prompt)
against a 32k context window, and truncation is silent (failure 4 in §4.4).
Mitigations in place: every agent profile enables only the `terminal` and
`file_editor` tools (no browser tools, no `switch_llm`), the skill deny-list
removes a large block of injected prompt, the role prompts are short, and the
team chat passed to each prompt is capped at four messages of 300 characters.
No measured scaling curve exists.

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
reasoning. The endpoint was moved to `qwen2.5:7b-instruct`, which has no thinking
mode to suppress, and later to `llama3.1:8b` for the coders only (§2).

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

**Open items.**

- Fix rounds rarely help. At temperature 0 a coder given its failures tends to
  rewrite the same code, so the keep-if-better check usually restores the
  previous version (both kept runs: every fix after the first round rejected).
  A stronger coder model, or a higher `CODER_TEMPERATURE` for a model that
  stays reliable at it, is the lever.
- One of 11 tests fails in the latest run (§5.4).
- A full run takes about 15–20 minutes on a 16 GB Mac.

---

## 9. Reproducing

`SETUP.md` is the reproduction guide: prerequisites, both endpoints, toolchain
configuration, and the commands that produce architecture output, an implemented
feature, executed tests, updated docs, and a deployment-validation step.

Verification entry points:

```bash
python3 scripts/demo.py                # the six-stage run, then a summary of the results
python3 scripts/demo.py --show         # the summary of the last run only
python3 scripts/pipeline.py --check    # endpoints, proxy, agents
python3 scripts/pipeline.py            # the six-stage run on its own
python3 scripts/pipeline.py --compare RUN_A RUN_B
./docker/validate.sh                   # deployability checks
```

---

## 10. Deliverables and where they stand

| Deliverable | Artefact | State |
|---|---|---|
| Synopsis, 7–10 pages | this document | complete |
| Setup guide | `SETUP.md` | complete |
| Architecture output | `docs/{components,api,deployment,decisions,handoff}.md` | produced by the agent |
| At least one implemented feature | `workspace/demo-project/src/calc/` | produced by the two coders |
| Tests executed + results | `workspace/demo-project/QUALITY.md` | 10 of 11 pass in the latest run |
| Docs updated | `workspace/demo-project/README.md` | produced by the docs agent |
| Deployment validation step | `docker/validate.sh`, reported in `docs/deployment-validation.md` | run every pipeline run |

The honest summary: the workflow delivers every artefact unattended on two
small local models. Quality is bounded by those models — the documents are
thin, and fix rounds rarely improve the code (§8).

## 11. Review of another group's work

To be completed after delivery, per the assignment. Not yet written.
