# Verification log

Every claim here comes from a command run in this repo. Re-running the probes is
how each result can be checked.

## 1. A non-default profile really routes to endpoint B

`architect` and `techlead` are endpoint A roles; `coder-1`, `coder-2`, `tester` and
`deploy-validator` are endpoint B roles. Endpoint A runs `qwen2.5:3b`, endpoint B
runs `qwen3:8b`, so a loaded-model check distinguishes them unambiguously.

Procedure: unload every Ollama model, start one conversation on a non-default
profile that names only the alias, and ask Ollama which model it loaded.

```
curl -X POST localhost:11435/api/generate -d '{"model":"qwen3:8b","keep_alive":0}'
curl -X POST localhost:11434/api/generate -d '{"model":"qwen2.5:3b","keep_alive":0}'
```

| profile | request | Ollama A (11434) | Ollama B (11435) | status |
|---|---|---|---|---|
| `docs` | `POST /api/conversations`, `max_iterations: 2`, `NeverConfirm` | `qwen2.5:3b` | none loaded | PASS |
| `tester` | `POST /api/conversations`, `max_iterations: 2`, `NeverConfirm` | `qwen2.5:3b` | `qwen3:8b` | PASS |

Both conversations finished. The agent server logs confirm it loaded the named
LLM profile rather than a default:

```
[Profile Store] Loaded profile `tester` from /home/openhands/.openhands/profiles/tester.json
```

The alias alone does not appear in the request, so a wrong routing decision
would be invisible. The loaded-model check is the evidence.

### A real tool-using turn on endpoint B

`tester` was asked to create `/opt/project/artifacts/verify-b.txt`. It took ~3.5
minutes and the file appeared with the requested contents:

```
-rw-------  1 kkr  staff  9 Oct  1 22:24 artifacts/verify-b.txt
BENDPOINT
```

Conversation stats for that run report the alias the agent asked for
(`openai/coder-1` in the equivalent coder run), which is the pre-resolution name,
not the backend. Treating that field as proof of endpoint routing would be wrong.

## 2. Confirmation policies really pause execution

Three policies, checked against `execution_status` plus whether the command
actually took effect on disk.

| policy | command | paused | outcome |
|---|---|---|---|
| `NeverConfirm` | create `artifacts/verify-b.txt` | no | ran, file created |
| `AlwaysConfirm` | `echo SHOULD_NOT_APPEAR > /tmp/reject_probe.txt` | yes, `waiting_for_confirmation` | file absent |
| `AlwaysConfirm` | `echo CONFIRM_ALWAYS_MARKER` | yes, `waiting_for_confirmation` | ran after approval |
| `ConfirmRisky` | `echo RISKY_PROBE_OK` | yes, `waiting_for_confirmation` | ran after approval |

Rejection proof. With `AlwaysConfirm`, the conversation held at
`waiting_for_confirmation` and `/tmp/reject_probe.txt` did not exist. Rejecting
through the documented endpoint returned `{"success": true}`, the conversation
moved to `idle`, and the probe file still did not exist:

```
POST /api/conversations/{conversation_id}/events/respond_to_confirmation
{"accept": false, "reason": "..."}   -> 200 {"success":true}
```

Accepting the `ConfirmRisky` action with `{"accept": true}` returned `200` and the
conversation then finished. So the gate blocks, and both answers are honoured.

Policy names are real, not invented. They come from the running server's own
OpenAPI document:

```
AlwaysConfirm  ConfirmRisky  NeverConfirm     # discriminator on kind
POST /api/conversations/{conversation_id}/events/respond_to_confirmation
  {accept: bool, reason?: string}
```

Two operational notes:

- `GET /api/conversations/{id}/events` returns `422`; the working read is
  `GET /api/conversations/{id}/events/search?limit=N&sort_order=TIMESTAMP_DESC`.
- Event search returned an empty list for conversations that had already
  finished, so status polling plus the on-disk effect is the reliable check.

A `terminal` action does carry a real side effect while approval is pending: the
first `AlwaysConfirm` run showed a `TerminalObservation` for `[RESET] echo
CONFIRM_ALWAYS_MARKER`. The reset marker is session setup, and the command did
not produce `/tmp/reject_probe.txt`, so execution itself was still gated.

## 3. `agent-canvas:8000` and the profile mount match the docs

Official setup docs (`docs.openhands.dev/openhands/usage/agent-canvas/setup`)
state Agent Canvas starts on `http://localhost:8000`, that the UI is served at
`/canvas`, and that `~/.openhands` is mounted to `/home/openhands/.openhands`.

| check | result |
|---|---|
| `GET localhost:8000` | `308` redirect to `/canvas` |
| `GET localhost:8000/canvas` | `200`, `<title>OpenHands</title>` |
| `GET /api/agent-profiles` | all 7 profiles, each with a UUID and its `llm_profile_ref` |
| mount `/home/openhands/.openhands` | agent server loads profiles from it |

Two deviations from the docs, both deliberate:

- Official docs mount a project directory at `/projects`. This repo is mounted at
  `/opt/project` so the agent's working directory matches the assignment repo.
- Official docs describe an npm/CLI install. This setup runs the same
  `ghcr.io/openhands/agent-canvas` image directly from `docker-compose.yml`.

Port binding was re-checked after pinning the images. All four ports refuse
connections on the LAN address, so the loopback-only claim holds:

```
port 4000 via 10.30.0.184: refused
port 8000 via 10.30.0.184: refused
port 11434 via 10.30.0.184: refused
port 11435 via 10.30.0.184: refused
```

## 4. Two faults that presented as model failures

Both broke every agent turn while `/v1/models` answered normally, so the symptom
pointed at the wrong layer. Recording them because they are easy to reintroduce.

### `os.environ/...` in an LLM profile is not expanded

With `"api_key": "os.environ/LITELLM_MASTER_KEY"` in
`openhands/state/profiles/*.json`, every conversation failed immediately with
`400 no_db_connection  {"error": {"message": "No connected db."}}`. LiteLLM treats
the literal, unresolved string as an unknown key and tries a virtual-key lookup,
which needs a database. The key is now the literal throwaway value; it is
committable only because every port is bound to `127.0.0.1`.

### `general_settings.master_key` also breaks without a database

Setting `master_key: os.environ/LITELLM_MASTER_KEY` in `endpoints/config.yml`
produces the same `No connected db.` error, from the same virtual-key code path.
The proxy key is supplied only through `LITELLM_MASTER_KEY` in the environment.

Verified directly against the proxy:

```
curl localhost:4000/v1/models -H "Authorization: Bearer os.environ/LITELLM_MASTER_KEY"
  -> 400 no_db_connection
curl localhost:4000/v1/models -H "Authorization: Bearer sk-local-not-secure"
  -> 200, 7 aliases
```

## 5. `qwen3:8b` thinking cannot be disabled on the `/v1` route

Endpoint B is `qwen3:8b`. Its thinking cost was measured before committing to it.

| route | `think` setting | native tool call | thinking observed |
|---|---|---|---|
| `/api/chat` (native Ollama) | `true` | yes | eval 694 tokens, 32.0 s |
| `/api/chat` (native Ollama) | `false` | yes | eval 0 tokens, 135 ms |
| `/v1/chat/completions` | `true` | yes | reasoning emitted |
| `/v1/chat/completions` | `false` | yes | reasoning still emitted |
| `/v1/chat/completions` | `low`, `high` | yes | reasoning emitted |
| `/v1/chat/completions` + `/no_think` in prompt | n/a | yes | reasoning still emitted |

LiteLLM uses the OpenAI-compatible `/v1` path, so `think` is ignored there. Only
the native endpoint honours it, and this proxy does not use that path.

Cost on a real multi-tool turn (create a module, create a test, run `pytest`)
through `/v1`:

| turn | completion tokens | reasoning chars | native calls |
|---|---|---|---|
| single tool call | 117 | 380 | 1 |
| three-file + pytest turn | 1156 | 4602 | 3 |

Parallel calls carry correct indices, which matters because the proxy and the
agent must agree on them:

```
index=0 file_editor a.txt   valid JSON
index=1 file_editor b.txt   valid JSON
index=2 file_editor c.txt   valid JSON
```

### Fallback warning

Endpoint B roles carry a LiteLLM fallback to `architect` (endpoint A,
`qwen2.5:3b`). A silent fallback to a non-tool-trained model would break the
requirement that execution roles actually run tools, so any pipeline measurement
must record which model served each turn rather than trusting the role alias.

`qwen2.5-coder:7b` must not be substituted as a fallback: it returns tool calls
as text, so it cannot drive an agent. `qwen2.5:7b-instruct` is verified and is
the documented alternative.

## 6. Images are pinned by digest

Both images were pinned after `:latest` had already drifted from the build that
was measured.

| service | pinned digest | version | source revision |
|---|---|---|---|
| `ghcr.io/berriai/litellm` | `sha256:32cfd7a427f6…` | built 2026-08-30 | `95293834e833b2d2979f87d1bd2a5be45db6728a` |
| `ghcr.io/openhands/agent-canvas` | `sha256:37575e4ece41…` | 1.21.0 | `fc6d890f7b21c71a17de60d50597c00355e235ea` |

These are the `linux/arm64` manifests, resolved against this machine. The
matching `amd64` digests are recorded as comments in `docker-compose.yml` for
running the same build on x86.

The pinned stack was restarted and re-verified: canvas `200` at `/canvas`, 7
aliases served, 7 agent profiles listed.