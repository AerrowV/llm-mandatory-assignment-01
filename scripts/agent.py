#!/usr/bin/env python3
"""Bring up the stack, show its state, and hand one role to an agent.

    python3 scripts/agent.py                 # start everything, run the architect
    python3 scripts/agent.py tester          # run a different role
    python3 scripts/agent.py "add a /health route"
    python3 scripts/agent.py --check         # just report state, change nothing
    python3 scripts/agent.py --check --run    # report state, then run a role

    python3 scripts/agent.py --confirm risky coder
    python3 scripts/agent.py --confirm always architect

Roles are architect, techlead, coder, tester, docs, deploy-validator. Each has
its own agent profile, so each resolves to its own LiteLLM alias.

--confirm is the control mechanism for non-functional requirement 1:
    never   no prompts; the only setting an unattended pipeline can use
    risky   ask before shell commands and destructive file operations
    always  ask before every action

Standard library only. See SETUP.md for what the pieces are.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "openhands" / "prompts"
LITELLM = "http://localhost:4000"
AGENT = "http://localhost:8000"
API_KEY = ROOT / "openhands" / "state" / "agent-canvas" / "api-key.txt"
WORKDIR = "/opt/project"  # where the repo is mounted inside the container

# The assignment wants two separate model servers, not two models on one.
SERVERS = [("endpoint A", 11434), ("endpoint B", 11435)]
KEY = "sk-local-not-secure"  # throwaway loopback key, matches endpoints/.env

# Role -> prompt file stem. The role name is also the LiteLLM alias and the
# name of its agent profile, so `run_role("architect")` resolves all three
# from this one table.
#
# coder-1 and coder-2 are the two parallel workers. They share one prompt and
# one model, and are distinguished only by name, so the pipeline can point
# each at a different git worktree and run them concurrently. That is the
# N >= 2 worker fan-out for functional requirement 3.
ROLES = {
    "architect": "01-architect",
    "techlead": "02-tech-lead",
    "coder-1": "03-implementation",
    "coder-2": "03-implementation",
    "tester": "04-testing",
    "docs": "05-documentation",
    "deploy-validator": "06-deployment",
}

# Non-functional requirement 1 wants a control mechanism: ask-before-edit, or
# plan + diffs reviewed before execution. OpenHands exposes these as a
# confirmation policy per conversation, so it is a run-time choice rather than
# a hardcoded constant. "never" keeps unattended pipeline runs possible;
# "risky" gates shell commands and destructive file operations, which is the
# closest available thing to ask-before-run.
CONFIRMATION = {
    "never": {"kind": "NeverConfirm"},
    "risky": {"kind": "ConfirmRisky"},
    "always": {"kind": "AlwaysConfirm"},
}

DONE = {"finished", "error", "stopped", "terminated", "paused", "idle"}


def ok(msg):
    print(f"  [ok]   {msg}")


def warn(msg):
    print(f"  [warn] {msg}")


def bad(msg):
    print(f"  [FAIL] {msg}")


def get(url, payload=None, timeout=30, headers=None):
    """HTTP GET or POST, returns parsed JSON or None if unreachable."""
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=hdrs,
                                 method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
    except (urllib.error.URLError, OSError, ValueError):
        return None
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            return {"status": 409}
        bad(f"{url} -> {exc.code}: {exc.read().decode()[:200]}")
        return None
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}  # reachable, but served HTML rather than JSON


def agent_api(path, payload=None, timeout=300):
    """Call the OpenHands server with its session key."""
    if not API_KEY.exists():
        bad(f"missing {API_KEY} - is the stack running?")
        return None
    return get(f"{AGENT}{path}", payload, timeout,
               {"X-Session-API-Key": API_KEY.read_text().strip()})


def models_on(port):
    data = get(f"http://localhost:{port}/api/tags", timeout=5)
    return None if data is None else [m["name"] for m in data.get("models", [])]


def start_stack():
    """docker compose up, then wait for both services to answer."""
    subprocess.run(["docker", "compose", "up", "-d"], cwd=ROOT,
                   capture_output=True, text=True)
    for name, url in (("litellm", f"{LITELLM}/health/liveliness"), ("openhands", AGENT)):
        for _ in range(90):
            if get(url, timeout=3) is not None:
                break
            time.sleep(2)
        else:
            bad(f"{name} never came up - docker compose logs --tail=40 {name}")
            return False
    # The API key is written during startup, after the port opens.
    for _ in range(15):
        if API_KEY.exists():
            return True
        time.sleep(2)
    bad(f"openhands never wrote {API_KEY}")
    return False


def show_state():
    print("\n-- model servers --")
    up = True
    for name, port in SERVERS:
        found = models_on(port)
        if found is None:
            bad(f"{name}  localhost:{port}  not running")
            up = False
        else:
            ok(f"{name}  localhost:{port}  {', '.join(found) or 'no models'}")

    print("\n-- stack --")
    for name, url in (("litellm", f"{LITELLM}/health/liveliness"), ("openhands", AGENT)):
        (ok if get(url, timeout=5) is not None else bad)(f"{name:<10} {url}")

    print("\n-- routing --")
    data = get(f"{LITELLM}/v1/models", timeout=10,
               headers={"Authorization": f"Bearer {KEY}"})
    if data is None or not data.get("data"):
        bad("litellm is not answering /v1/models")
        return up
    for model in sorted(m["id"] for m in data["data"]):
        ok(f"{model}  ->  a server in endpoints/config.yml")
    return up


def resolve_profile(role):
    """Find the agent profile whose llm_profile_ref matches the role.

    The role name is the join key across three layers: the prompt file, the
    LiteLLM alias, and the agent profile. Each role has its own profile, so
    binding a role to a different endpoint is a one-line edit in
    endpoints/config.yml plus a restart — nothing here changes.

    Returns (profile_id, llm_profile_name) or (None, None).
    """
    data = agent_api("/api/agent-profiles")
    if not data:
        return None, None
    for p in data.get("profiles", []):
        if p.get("name") == role:
            return p["id"], p.get("llm_profile_ref")
    return None, None


def run_role(target, confirm="never", workdir=WORKDIR):
    """Hand one role prompt to an agent and wait for it.

    `target` is a role name from ROLES, or a literal prompt string.
    `confirm` is one of CONFIRMATION.

    Returns the conversation id, or None if the agent never started.
    """
    if confirm not in CONFIRMATION:
        bad(f"unknown confirmation mode {confirm!r}; "
            f"pick one of {', '.join(CONFIRMATION)}")
        return None

    prompt, label, role = target, "custom prompt", None
    if target in ROLES:
        role = target
        path = PROMPTS / f"{ROLES[role]}.md"
        if path.exists():
            prompt, label = path.read_text(), f"openhands/{path.name}"
        else:
            warn(f"{role}: no prompt at {path.relative_to(ROOT)}")

    if role:
        profile_id, llm_profile = resolve_profile(role)
        if not profile_id:
            bad(f"no agent profile named {role!r} "
                "(expected openhands/state/agent-profiles/%s.json)" % role)
            return None
        ok(f"{label}  ->  profile {role}  ->  {llm_profile}")
    else:
        data = agent_api("/api/agent-profiles")
        profile_id = next((p["id"] for p in (data or {}).get("profiles", [])
                           if p.get("name") == "architect"), None)
        if not profile_id:
            bad("no 'architect' agent profile to fall back on")
            return None
        ok(f"{label}  ->  profile architect (custom prompt)")

    conv = agent_api("/api/conversations", {
        "agent_profile_id": profile_id,
        "workspace": {"working_dir": workdir, "kind": "LocalWorkspace"},
        "initial_message": {"role": "user",
                            "content": [{"type": "text", "text": prompt}],
                            "run": True},
        "max_iterations": 100,
        "confirmation_policy": CONFIRMATION[confirm],
    })
    if not conv:
        return None
    cid = conv.get("conversation_id") or conv.get("id")
    if not cid:
        bad(f"no conversation id: {json.dumps(conv)[:200]}")
        return None
    ok(f"conversation {cid} - watch at {AGENT}")

    while True:
        state = str((agent_api(f"/api/conversations/{cid}", timeout=30) or {})
                    .get("execution_status", "?")).lower()
        if state in DONE:
            (ok if state == "finished" else warn)(f"finished: {state}")
            return cid
        time.sleep(5)


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    want_run = "--run" in args or not check_only

    confirm, rest = "never", []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--confirm" and i + 1 < len(args):
            confirm, i = args[i + 1], i + 2
        elif a.startswith("--confirm="):
            confirm, i = a.split("=", 1)[1], i + 1
        elif a in ("--check", "--run"):
            i += 1
        elif a.startswith("-"):
            bad(f"unknown flag {a}")
            return 1
        else:
            rest.append(a)
            i += 1

    if confirm not in CONFIRMATION:
        bad(f"unknown confirmation mode {confirm!r}; "
            f"pick one of {', '.join(CONFIRMATION)}")
        return 1

    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        bad("docker is not running")
        return 1

    if not check_only and not start_stack():
        return 1
    if not show_state():
        bad("model servers are down - see SETUP.md")
        return 1
    if not want_run:
        return 0

    print()
    run_role(rest[0] if rest else "architect", confirm=confirm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
