# How the workflow satisfies each functional requirement

*(Synopsis section — Kris. Companion to `SETUP.md` and `docs/requirements-audit.md`.)*

> **Status: INCOMPLETE.** This document describes the *intended* design. At the time
> of writing the six-role pipeline had not been run end to end, and no requirement
> below is satisfied by a produced artifact. Treat every "Met" as "mechanism
> exists, deliverable not produced". Requirements 5 and 6 were previously marked
> "Met"; both were downgraded to **NOT MET** because the documentation and
> deployment roles never ran and no artefact of theirs exists in the repo.

## The mechanism every requirement rides on

Roles are not hardcoded into the agent. They are a chain of three indirections, so
one config edit re-points a role at a different model server:

```
.env                                   the only file that is edited by hand
  +-> agent profile  (openhands/state/agent-profiles/<role>.json -> llm_profile_ref)
  +-> LLM profile    (openhands/state/profiles/<role>.json -> "openai/<alias>")
  +-> LiteLLM alias  (endpoints/config.yml -> api_base + model)
       -> endpoint A :11434  or  endpoint B :11435

role prompt (prompts/0*.md)            read at run time, names no server
```

The LLM profile names a **LiteLLM alias**, never a server. Which physical endpoint
an alias reaches is decided only in the proxy config, so moving a role between
endpoints is a one-line edit plus `docker compose restart litellm` — no rewiring.

**This chain is now wired.** Each role has its own agent profile and its own LLM
profile, and `scripts/agent.py` resolves the profile by role name rather than
hardcoding a single `default`. Verified against the running server, which reports
seven distinct profile-to-role bindings. It was previously a single `default`
profile, so every role ran on endpoint A; that was corrected in Phase 1.

Routing is real but **untested against a real agent turn** — the aliases are
served and answer tool calls, but no role has yet produced an artifact, so this
is verified at the gateway layer only.

Handoff between roles is by **file in the repo**, not by conversation memory. The
repo is bind-mounted read-write at `/opt/project`, so each role reads its
predecessor's files and writes its own into the same tree. This part is real.

| # | Responsibility | Status |
| --- | --- | --- |
| 1 | Architecture | NOT MET — prompt + binding only, no artifacts produced |
| 2 | Tech lead | NOT MET — prompt + binding only, no tickets produced |
| 3 | Implementation (N ≥ 2) | NOT MET — no fan-out, no worktrees, no code written |
| 4 | Testing & quality | NOT MET — no demo project, no tests, no quality report |
| 5 | Documentation | NOT MET — `README.md` is still the 29-line project plan |
| 6 | Deployment validation | PARTIAL — compose/scripts exist but were hand-written, not produced by the deploy role |

---

## 1. Architecture — mechanism proven

`prompts/01-architect.md` binds the role to one artifact per required output:
component decomposition → `docs/components.md`, interface contracts →
`docs/api.md`, deployment topology → `docs/deployment.md`, and decision records →
`docs/decisions.md`. It closes with a mandatory `docs/handoff.md` so the next role
has an explicit entry point rather than inferring state.

The role is *intended* to be bound to endpoint A (`qwen2.5:3b`) via
`openhands/state/profiles/architect.json`. In practice every role resolves to
that same profile today — see the chain note above. Architecture work is
reasoning-heavy and tool-light, so a chat model on the planning endpoint is the
right capacity split, but this has not been demonstrated for the architect role
specifically.

**Evidence.** The write path this role depends on is the same one the demo
exercises: conversation `de896d48` issued 7 tool actions — `file_editor create`
on `/opt/project/artifacts/demo-report.md`, then five `view` calls to read it
back and confirm content. Artifact authoring under `/opt/project` is therefore
demonstrated, not assumed. `docs/components.md` and siblings have not been
generated yet.

## 2. Tech lead — mechanism proven

`prompts/02-tech-lead.md` consumes `docs/handoff.md` plus the rest of `docs/`
and emits one ticket file per task carrying exactly the three fields the
requirement names: an explicit **scope boundary** ("what it does NOT cover"),
**acceptance criteria** phrased as 2–3 checkable conditions, and **declared
dependencies**. Ordering is a separate artifact, `tickets/list.md`, so dependency
graph and execution order are reviewable on their own.

Two design choices are worth calling out. The prompt forbids stalling on
questions — an unattended agent that waits for an "ok" that can never arrive
writes nothing, so ambiguity is recorded in `docs/questions.md` and the ticket is
written anyway with the assumption marked. The role is *intended* to share
endpoint A with the architect — ticket decomposition is the same reasoning-shaped
work, and keeping it on one endpoint leaves endpoint B's capacity free for code.
That intent is not yet enforced by config.

**Gap.** `tickets/` contains only a README. The prompt is complete and bound; it
has not been run end to end.

## 3. Implementation — partial, and the honest weak point

The requirement is N ≥ 2 workers parallelising, or a credible equivalent, plus
multi-file changes across a repository.

**Multi-file change: demonstrated.** `terminal` execution works, not just
`file_editor`. Conversation `3a4b16fb` ran a 5-action chain — `think`, a shell
command, `python3` execution of the result, then a heredoc write — producing a
working `fizzbuzz.py` on disk. Conversation `98132106` issued six actions across
repeated `file_editor create` calls, i.e. multi-file intent survived the round
trip. So the write-and-execute substrate is real.

**N ≥ 2 workers: designed, not yet orchestrated.** `scripts/agent.py` launches
**one** conversation and polls it to completion (`run_role`, then the `DONE`
loop). There is no fan-out and no per-worker git worktree. The evidence on disk
shows four conversations created within five minutes on 2026-09-30, but their
event windows do not overlap — they were sequential repeats, not parallel
workers. This is the requirement we have not yet earned.

The design is settled and cheap to build, because the substrate is already
there: `scripts/agent.py` needs only to (a) create one `git worktree` per
worker, (b) fire N `POST /api/conversations` with
`workspace.working_dir` pointed at each worktree and a *different*
`llm_profile_ref`, and (c) gate on exit code and emit a merge proposal. Worktrees
also hand us the reviewable per-worker diffs the reproducibility requirement
wants. Estimated as the single largest remaining piece of glue.

## 4. Testing & quality — partial

Two distinct layers exist, and they are deliberately separated.

*The harness layer.* `scripts/demo.py` is itself a quality gate. Its `verify`
phase reads the event log off the mounted state volume, counts `ActionEvent`s
(tool calls actually executed), flags observations where OpenHands set
`is_error`, and checks the artifact is non-empty and has the expected content.
It exits non-zero unless tools ran *and* the file landed, so it can gate a
script. `--smoke` isolates the layer below the agent: a structured `tool_calls`
round trip straight through LiteLLM with no OpenHands involved. A green smoke
test with a red verify localises the fault to the agent rather than the wiring —
which is exactly the diagnosis that unblocked this project.

*The role layer.* `prompts/04-testing.md` requires creating and running tests
and emitting a quality report with test results, static checks, and known
limitations/risks — the three required subsections are all named in the prompt.

**Gap.** There is no demo project to test. `workspace/` holds no source, no test
runner, and no linter, so the testing role currently has nothing to exercise.
Both the script and the prompt are stubs past `## Output Format` and need
finishing before a run means anything.

## 5. Documentation — NOT MET

The prompt is complete; the deliverable is not. `prompts/05-documentation.md` is
the most complete of the six: developer and user
docs, README setup/config/usage/troubleshooting, API reference with auth,
endpoints, parameters, responses and errors, operational runbooks (deploy,
monitor, backup, incident, rollback), and design documents. It carries two
constraints that protect the rest of the workflow: *do not invent undocumented
behaviour* and *do not expose secrets, credentials or private URLs* — the second
matters here because `LITELLM_MASTER_KEY` sits in plain text in committed config.

The deliverable it feeds is `SETUP.md`, which is real: prerequisites table, both
endpoints started as separate `ollama serve` processes with separate model dirs,
role invocation, and a file-by-file map. Its most valuable content is the
**four failure modes that silently break agents**, each with the measurement that
identified it — for example that LiteLLM's `ollama_chat/` handler emits every
parallel tool call under `index=0` and concatenates the argument fragments into
unparseable JSON, which reads as a flaky weak model but is a serialisation bug.

**Gap.** `README.md` is still the original 29-line project plan, not
user-facing setup docs. The documentation role has not run, so there is no
developer doc, no runbook, and no design document produced by an agent.
`SETUP.md` was hand-written and is a genuine deliverable, but it is not evidence
that the documentation *responsibility* is covered.

## 6. Deployment validation — PARTIAL

The four permitted axes are each represented in the repo, and the underlying
toolchain validates *programmatically* rather than by assertion:

- **Container build/deploy config.** `docker-compose.yml` defines the two
  services (`litellm`, `openhands`) with a `healthcheck` on
  `/health/liveliness` and `depends_on: service_healthy`, so the agent server
  cannot start before the gateway can route. It is the artefact under test, not
  just toolchain plumbing.
- **Deployment script.** `scripts/agent.py --check` is a preflight that verifies
  Docker, probes both Ollama endpoints, confirms both containers answer, and
  prints the live routing table from `/v1/models` — then changes nothing. It
  exits non-zero if an endpoint is down.
- **Environment/config documentation.** `SETUP.md` §2–3, the file table, and
  `.env.example`, which documents every setting in one place. `endpoints/config.yml`
  and the profile files are generated from `.env` by `scripts/config.py` and are
  committed, so the intended config is reviewable in git;
  `python3 scripts/config.py --check` fails if they have drifted from `.env`.
- **Deployment checklist.** `SETUP.md`'s four-failure-mode section is the
  pre-flight check an operator runs first.

The security baseline holds: both Ollama servers bind `127.0.0.1` only, and both
published ports are `127.0.0.1:4000:4000` and `127.0.0.1:8000:8000`, so nothing
unauthenticated is reachable off-host. `docs/requirements-audit.md` records that
this was a real defect — compose originally published `4000:4000` on all
interfaces and LiteLLM answered on the LAN IP — now fixed and verified closed.

---

## Summary

**No functional requirement is currently satisfied by a produced artefact.**
Requirements 1–5 are NOT MET; 6 is PARTIAL.

The underlying substrate is real and worth keeping: an agent can write files and
run shell commands, and the gateway routes by config. What is missing is
everything above that substrate — the six roles have not been run in order, per-role
endpoint binding is not wired, there is no worker fan-out, and there is no demo
project. The gaps are scoping and sequencing, not capability.

Two gaps carry the most risk: **N ≥ 2 worker fan-out** (FR3, the weakest
requirement) and **a demo project to test** (FR4).

The lesson worth carrying into the synopsis is that every hard blocker we hit was
a *wiring* fault dressed as a *model quality* fault — tool calls serialised into
unparseable JSON, prompts silently truncated against an under-declared context
window, a model list drifting from its config file. Each was found by splitting
the smoke test from the verify phase and measuring at the layer where it broke,
not by tuning the prompt.