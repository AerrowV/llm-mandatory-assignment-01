#!/usr/bin/env python3
"""Run the demo end to end and say plainly whether it worked.

    python3 scripts/demo.py            # preflight, smoke test, run, verify
    python3 scripts/demo.py --smoke    # tool-calling smoke test only
    python3 scripts/demo.py --task "..." architect
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent  # noqa: E402  same directory, and the stack logic lives there

ROOT = agent.ROOT
STATE = ROOT / "openhands" / "state" / "agent-canvas" / "conversations"
ARTIFACTS = ROOT / "artifacts"

# Absolute path inside the container, so the agent cannot invent a workspace.
DEMO_FILE = f"{agent.WORKDIR}/artifacts/demo-report.md"
DEMO_FILE_LOCAL = ARTIFACTS / "demo-report.md"
DEMO_MARKER = "Demo Report"

# Lives in prompts/ like every other role prompt, rendered with these values.
DEFAULT_TASK = agent.render_prompt(
    (agent.PROMPTS / "00-demo.md").read_text(), "demo", agent.WORKDIR,
    DEMO_FILE=DEMO_FILE, DEMO_MARKER=DEMO_MARKER)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "file_editor",
        "description": "Create or view a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string",
                            "enum": ["create", "view"],
                            "description": "create writes file_text, view reads path"},
                "path": {"type": "string", "description": "absolute file path"},
                "file_text": {"type": "string", "description": "content for create"},
            },
            "required": ["command", "path"],
        },
    },
}]

SMOKE_PROMPT = (f"Create the file {DEMO_FILE} containing the text 'OK'. "
                "Call file_editor; do not write a reply.")

ERRORY = ("error", "invalid", "not found", "does not exist", "failed",
          "traceback", "denied")

# An OpenHands request is ~20k tokens. A model declared below this gets its
# prompt silently truncated, then ignores the task and answers with unrelated text.
NEEDS_CONTEXT = 24576

# ---------------------------------------------------------------- phases

def preflight(start):
    print("\n== preflight ==")
    if agent.get(f"{agent.LITELLM}/health/liveliness", timeout=3) is None:
        if not start:
            agent.bad("stack is down - start it with: python3 scripts/agent.py")
            return False
        agent.ok("starting stack")
        if not agent.start_stack():
            return False
    return agent.show_state()

def context_guard():
    print("\n== context budget ==")
    data = agent.get(f"{agent.LITELLM}/v1/model/info", timeout=10,
                     headers={"Authorization": f"Bearer {agent.KEY}"})
    if not data or not data.get("data"):
        agent.warn("litellm did not report model info, skipping the check")
        return True
    healthy = True
    for entry in data["data"]:
        name = entry.get("model_name", "?")
        limit = (entry.get("model_info") or {}).get("max_input_tokens") or 0
        if limit >= NEEDS_CONTEXT:
            agent.ok(f"{name}: {limit} tokens declared")
        else:
            agent.bad(f"{name}: {limit} tokens declared, "
                      f"an OpenHands request needs ~{NEEDS_CONTEXT}")
            healthy = False
    return healthy

def smoke_test():
    print("\n== smoke test: structured tool call through LiteLLM ==")
    for model in ("coding-model", "architecture-model"):
        data = agent.get(f"{agent.LITELLM}/v1/chat/completions", {
            "model": model,
            "messages": [{"role": "user", "content": SMOKE_PROMPT}],
            "tools": TOOLS,
            "tool_choice": "auto",
            "temperature": 0,
        }, timeout=180, headers={"Authorization": f"Bearer {agent.KEY}"})
        if not data:
            agent.bad(f"{model}: no answer")
            continue
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        calls = message.get("tool_calls") or []
        if calls:
            fn = calls[0].get("function", {})
            args = fn.get("arguments")
            try:
                parsed = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                parsed = None
            agent.ok(f"{model}: tool_calls[0] = {fn.get('name')} "
                     f"{str(parsed or args)[:90]}")
        else:
            text = (message.get("content") or "")[:90].replace("\n", " ")
            agent.warn(f"{model}: no tool_calls, text was: {text!r}")

def resolve_task(argv, custom):
    role = next((a for a in argv if a in agent.ROLES), None)
    if role:
        stem = agent.ROLES[role]
        path = agent.PROMPTS / f"{stem}.md"
        agent.ok(f"role prompt prompts/{path.name}")
        return agent.render_prompt(path.read_text(), role,
                                   agent.workdir_for(role)), False
    if custom is not None:
        agent.ok("custom task, artifact check will be skipped")
        return custom, False
    agent.ok(f"built-in demo task, expects {DEMO_FILE}")
    return DEFAULT_TASK, True

def wait(cid, timeout):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        state = str((agent.agent_api(f"/api/conversations/{cid}", timeout=30) or {})
                    .get("execution_status", "?")).lower()
        if state == last and state in agent.DONE:
            return state
        last = state
        time.sleep(5)
    return f"timeout after {timeout}s"

def events(cid):
    directory = STATE / cid.replace("-", "") / "events"
    if not directory.is_dir():
        agent.warn(f"no event log on disk for {cid} (has the state volume moved?)")
        return []
    out = []
    for path in sorted(directory.glob("event-*.json")):
        try:
            out.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return out

def reply_text(log):
    said = [e for e in log if e.get("kind") == "MessageEvent"
            and e.get("source") == "agent"]
    if not said:
        return None
    content = (said[-1].get("llm_message") or {}).get("content") or []
    return "".join(part.get("text", "") for part in content
                   if isinstance(part, dict)).strip()

def failed(observation):
    if not observation:
        return False
    if "is_error" in observation:
        return bool(observation["is_error"])
    text = json.dumps(observation).lower()
    return any(word in text for word in ERRORY)

def verify(cid, artifact=DEMO_FILE_LOCAL, marker=DEMO_MARKER):
    print("\n== verify ==")
    log = events(cid)
    actions = [e for e in log if e.get("kind") == "ActionEvent"]
    observations = [e for e in log if e.get("kind") == "ObservationEvent"]

    if not actions:
        agent.bad(f"0 tools executed ({len(log)} events, no ActionEvent)")
        said = reply_text(log)
        if said:
            agent.bad(f"the agent replied with text instead: {said[:160]!r}")
            if DEMO_FILE not in said and DEMO_MARKER not in said:
                agent.warn("the reply never mentions the task - the model lost "
                           "it, usually a context-window problem")
        else:
            agent.bad("the agent said nothing and called nothing")
    else:
        commands = [str((a.get("action") or {}).get("command")
                        or a.get("tool_name") or "?") for a in actions]
        agent.ok(f"{len(actions)} tools executed: {', '.join(commands)}")
        bad_obs = [o for o in observations if failed(o.get("observation"))]
        (agent.bad if bad_obs else agent.ok)(
            f"{len(bad_obs)} of {len(observations)} tool results reported an error")

    landed = False
    if artifact is None:
        agent.warn("artifact check skipped (custom task, no known output file)")
    elif not artifact.exists():
        agent.bad(f"missing {agent.rel(artifact)}")
    else:
        text = artifact.read_text()
        first = text.lstrip().splitlines()[0] if text.strip() else ""
        if not text.strip():
            agent.bad(f"{agent.rel(artifact)} is empty")
        elif marker and marker not in text:
            agent.bad(f"{agent.rel(artifact)} has no '{marker}'")
        elif not first.startswith("#"):
            agent.bad(f"{agent.rel(artifact)} starts {first[:40]!r}, "
                      "expected a markdown heading")
            agent.warn("the tool call worked but the content is not what was "
                       "asked for - a small-model limit, not a wiring fault")
        else:
            agent.ok(f"{agent.rel(artifact)} "
                     f"({len(text.splitlines())} lines)")
            landed = True
    return landed

def record(summary):
    try:
        run_dir = ARTIFACTS / "runs" / datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ")
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "demo.json").write_text(json.dumps(summary, indent=2) + "\n")
    except OSError as exc:
        agent.warn(f"could not record run: {exc}")
        return
    print(f"\nrecorded in {agent.rel(run_dir)}")

# ---------------------------------------------------------------- main

def flag_value(argv, name, fallback):
    if name not in argv:
        return fallback
    after = argv[argv.index(name) + 1:]
    return after[0] if after and not after[0].startswith("-") else None

def main():
    argv = sys.argv[1:]
    if any(a in ("-h", "--help", "help") for a in argv):
        print((__doc__ or "").strip())
        return 0

    check_only = "--check" in argv
    smoke_only = "--smoke" in argv
    custom = flag_value(argv, "--task", None)
    timeout = int(flag_value(argv, "--timeout", 600) or 600)

    if smoke_only:
        preflight(start=False)
        smoke_test()
        return 0
    if check_only:
        return 0 if preflight(start=False) else 1
    if not preflight(start=True):
        return 1

    print()
    smoke_test()
    context_guard()

    print("\n== demo run ==")
    prompt, known = resolve_task(argv, custom)
    cid = agent.run_role(prompt)
    if not cid:
        agent.bad("no conversation was created")
        return 1

    status = wait(cid, timeout)
    (agent.ok if status == "finished" else agent.warn)(f"agent status: {status}")
    print()

    artifact = DEMO_FILE_LOCAL if known else None
    passed = verify(cid, artifact, DEMO_MARKER if known else None)

    record({"conversation_id": cid, "status": status, "tools_executed":
            sum(1 for e in events(cid) if e.get("kind") == "ActionEvent"),
            "artifact": str(agent.rel(artifact)) if artifact else None,
            "artifact_ok": passed})
    print(f"\ndemo {'PASSED' if passed else 'FAILED'} - "
          f"logs: docker compose logs openhands")
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())