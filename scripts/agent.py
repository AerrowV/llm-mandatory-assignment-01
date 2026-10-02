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

python3 scripts/agent.py --workers coder-1,coder-2   # run both in parallel
    python3 scripts/agent.py --workers coder-1 --merge    # then merge the branches

Standard library only. See SETUP.md for what the pieces are.
"""

import concurrent.futures
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


def scope_prompt(prompt, role, workdir):
    """Tell the agent where it is, and make sure it cannot escape.

    Two problems this prevents. The role prompts mandate absolute paths like
    /opt/project/docs/x.md, which is correct for a role working in the repo root
    but wrong for a worker in a worktree: it would write straight into the main
    checkout and leave the worker's branch empty. And a role that is told to
    "run in /opt/project" but actually sits in a worktree will wander outside
    the branch it owns.
    """
    if not role or workdir == WORKDIR:
        return prompt
    return (
        f"# WHERE YOU ARE RUNNING\n\n"
        f"You are worker `{role}`. Your working directory is `{workdir}`, a git\n"
        f"worktree on branch `agent/{role}`. Every path you write must start with\n"
        f"`{workdir}/`. Do not write to `/opt/project/` directly: that is the main\n"
        f"checkout and your work would not land on your branch.\n\n"
        f"Your changes are merged back for you afterwards. You do not need to run\n"
        f"git commands, and you should not try to switch branches.\n\n"
        f"---\n\n{prompt}"
    )


def run_role(target, confirm="never", workdir=WORKDIR, started=None, finished=None):
    """Hand one role prompt to an agent and wait for it.

    `target` is a role name from ROLES, or a literal prompt string.
    `confirm` is one of CONFIRMATION.
    `started` and `finished` are optional dicts; the conversation's wall-clock
    start and end are recorded in them so a caller can prove whether two runs
    actually overlapped.

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
            prompt = scope_prompt(path.read_text(), role, workdir)
            label = f"openhands/{path.name}"
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

    if started is not None:
        started["cid"] = cid
        started["t0"] = time.time()
    while True:
        state = str((agent_api(f"/api/conversations/{cid}", timeout=30) or {})
                    .get("execution_status", "?")).lower()
        if state in DONE:
            if finished is not None:
                finished["cid"] = cid
                finished["t1"] = time.time()
            (ok if state == "finished" else warn)(f"finished: {state}")
            return cid
        time.sleep(5)


WORKTREES = ROOT / ".worktrees"


def git(*args, check=True):
    """Run git in the repo. Returns (returncode, stdout+stderr)."""
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    if check and proc.returncode:
        bad(f"git {' '.join(args)} -> {out[:300]}")
    return proc.returncode, out


def make_worktree(worker):
    """Give `worker` its own branch and checkout so two workers cannot collide.

    The directory lives inside the repo, which matters: the repo is bind-mounted
    at /opt/project, so the agent sees the worktree at the same relative path it
    was created at and writes land on the host.

    Returns the container-visible working directory, or None on failure.
    """
    branch = f"agent/{worker}"
    path = WORKTREES / worker
    WORKTREES.mkdir(exist_ok=True)
    if path.exists():
        git("worktree", "remove", "--force", str(path))
    # -B resets the branch so a rerun starts clean instead of stacking on the
    # previous run's commits.
    code, out = git("worktree", "add", "-B", branch, str(path))
    if code:
        return None
    ok(f"worktree {path.relative_to(ROOT)} on branch {branch}")
    return f"{WORKDIR}/{WORKTREES.name}/{worker}"


def drop_worktree(worker, merge=True):
    """Merge a worker's branch back, then remove the worktree.

    Returns True if the merge was clean. A conflict is reported, not silently
    resolved: the caller has to look at it.
    """
    path = WORKTREES / worker
    if not path.exists():
        return False
    if merge:
        changed = git("diff", "--name-only", "HEAD", f"agent/{worker}")[1]
        if not changed:
            warn(f"{worker}: branch has no changes, nothing to merge")
            return True
        ok(f"{worker} changed {len(changed.splitlines())} file(s): "
           + ", ".join(c.split("/")[-1] for c in changed.splitlines()[:6]))
        code, out = git("merge", "--no-edit", f"agent/{worker}")
        if code:
            bad(f"merge of {worker} conflicted - resolve manually:\n{out[:600]}")
            return False
        ok(f"merged agent/{worker}")
    git("worktree", "remove", "--force", str(path))
    return True


def run_workers(workers, confirm="never"):
    """Run every worker concurrently, each in its own worktree.

    This is the N >= 2 fan-out for functional requirement 3. It is only real if
    the conversations overlap in time, so the result reports each worker's start
    and end and the overlap window rather than asserting that it was parallel.
    """
    for w in workers:
        if w not in ROLES:
            bad(f"unknown worker {w!r}; pick from {', '.join(sorted(ROLES))}")
            return {}
    workdirs = {}
    for w in workers:
        wd = make_worktree(w)
        if not wd:
            return {}
        workdirs[w] = wd

    marks = {w: {"started": {}, "finished": {}} for w in workers}
    print(f"\n-- {len(workers)} workers in parallel --")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(workers)) as pool:
        futures = {
            w: pool.submit(run_role, w, confirm, workdirs[w],
                           marks[w]["started"], marks[w]["finished"])
            for w in workers
        }
        results = {w: f.result() for w, f in futures.items()}

    report_parallelism(workers, marks)
    for w in workers:
        if results.get(w):
            ok(f"{w}: conversation {results[w]}")
        else:
            bad(f"{w}: no conversation")
    return {"workdirs": workdirs, "conversations": results, "marks": marks}


def report_parallelism(workers, marks):
    """Print measured overlap, not an assumption of it.

    Concurrent execution means the intervals [t0, t1] intersect. If they merely
    run one after another, the total span equals the sum of the runs and this
    says so.
    """
    spans = []
    for w in workers:
        m = marks[w]
        if "t0" in m["started"] and "t1" in m["finished"]:
            spans.append((w, m["started"]["t0"], m["finished"]["t1"]))
    if len(spans) < 2:
        return
    lo = max(s[1] for s in spans)
    hi = min(s[2] for s in spans)
    overlap = hi - lo
    print("\n-- measured concurrency --")
    base = min(s[1] for s in spans)
    for w, t0, t1 in sorted(spans, key=lambda s: s[1]):
        print(f"  {w:<12} +{t0 - base:6.1f}s to +{t1 - base:6.1f}s  ({(t1 - t0):6.1f}s)")
    total = max(s[2] for s in spans) - min(s[1] for s in spans)
    if overlap > 0:
        ok(f"genuinely parallel: {overlap:.1f}s of shared wall-clock time")
    else:
        warn(f"serialised: no overlap, whole fan-out took {total:.1f}s")


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    want_run = "--run" in args or not check_only

    confirm, rest = "never", []
    workers = None
    do_merge = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--confirm" and i + 1 < len(args):
            confirm, i = args[i + 1], i + 2
        elif a.startswith("--confirm="):
            confirm, i = a.split("=", 1)[1], i + 1
        elif a == "--workers" and i + 1 < len(args):
            workers, i = [w.strip() for w in args[i + 1].split(",") if w.strip()], i + 2
        elif a.startswith("--workers="):
            workers = [w.strip() for w in a.split("=", 1)[1].split(",") if w.strip()]
            i += 1
        elif a == "--merge":
            do_merge, i = True, i + 1
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
    if do_merge:
        for w in (workers or ["coder-1", "coder-2"]):
            drop_worktree(w, merge=True)
        return 0
    if workers:
        result = run_workers(workers, confirm)
        if not result.get("conversations"):
            return 1
        failed = [w for w, cid in result["conversations"].items() if not cid]
        return 1 if failed else 0
    run_role(rest[0] if rest else "architect", confirm=confirm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
