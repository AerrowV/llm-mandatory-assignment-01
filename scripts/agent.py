#!/usr/bin/env python3
"""Stack control and single-role runs.

    python3 scripts/agent.py --check          # preflight, changes nothing
    python3 scripts/agent.py coder-1 coder-2 --workers coder-1,coder-2
    python3 scripts/agent.py architect        # run one role prompt
    python3 scripts/agent.py coder-1 --yes    # skip confirmation prompts
"""

import concurrent.futures
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from config import (  # noqa: E402  sibling module, and the single place .env is read
    CONFIG_YML,
    ROLES,
    WORKER_MODULE,
    load_env,
    sync as sync_config,
)

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
FRAGMENTS = PROMPTS / "fragments"
API_KEY = ROOT / "openhands" / "state" / "agent-canvas" / "api-key.txt"

# Every setting below comes from .env, the only file to edit. `python3
# scripts/config.py` prints what the current file means.
ENV = load_env()

LITELLM = ENV["LITELLM_URL"]
AGENT = ENV["AGENT_URL"]
KEY = ENV["LITELLM_MASTER_KEY"]
WORKDIR = ENV["WORKDIR"]  # where the repo is mounted inside the container
DEMO = ENV["DEMO_PROJECT"]
MAX_ITERATIONS = int(ENV["MAX_ITERATIONS"])
STAGE_BUDGET = int(ENV["STAGE_BUDGET"])
DEFAULT_CONFIRMATION = ENV["CONFIRMATION"]

# The assignment requires two separate servers, not two models on one.
SERVERS = [(n, ENV[f"ENDPOINT_{l}_HOST"], int(ENV[f"ENDPOINT_{l}_PORT"]))
           for n, l in (("endpoint A", "A"), ("endpoint B", "B"))]

# NFR1 control mechanism. "risky" is the closest thing to ask-before-run: it
# gates shell commands and destructive file ops. "never" allows unattended runs.
CONFIRMATION = {
    "never": {"kind": "NeverConfirm"},
    "risky": {"kind": "ConfirmRisky"},
    "always": {"kind": "AlwaysConfirm"},
}

# "stuck" is OpenHands' loop detector giving up. It is terminal too: missing
# it here left the pipeline polling a dead conversation for two hours.
DONE = {"finished", "error", "stopped", "terminated", "paused", "idle", "stuck"}

def rel(path):
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)

def ok(msg):
    print(f"  [ok]   {msg}")

def warn(msg):
    print(f"  [warn] {msg}")

def bad(msg):
    print(f"  [FAIL] {msg}")

def probe_state(url, timeout=5):
    """Why a URL is unreachable, in words a reader can act on.

    get() returns None for a refused connection, a timeout and a proxy 403
    alike. Those need different fixes, so --check must not call all of them
    "not running".
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return "ok"
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 407):
            return "blocked by a proxy or firewall (HTTP %d)" % exc.code
        return "answered HTTP %d" % exc.code
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), socket.timeout):
            return "timed out"
        return "not running (connection refused)"
    except (OSError, ValueError):
        return "not running"


def get(url, payload=None, timeout=30, headers=None):
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
    if not API_KEY.exists():
        bad(f"missing {API_KEY} - is the stack running?")
        return None
    return get(f"{AGENT}{path}", payload, timeout,
               {"X-Session-API-Key": API_KEY.read_text().strip()})

def models_on(host, port):
    data = get(f"http://{host}:{port}/api/tags", timeout=5)
    return None if data is None else [m["name"] for m in data.get("models", [])]

def start_stack():
    try:
        sync_config()
    except Exception as exc:  # ConfigError, or an unreadable .env
        bad(f".env is not usable: {exc}")
        return False
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
    # Written during startup, after the port opens.
    for _ in range(15):
        if API_KEY.exists():
            return True
        time.sleep(2)
    bad(f"openhands never wrote {API_KEY}")
    return False

def show_state():
    print("\n-- configured in .env --")
    for name, url, model, served in config_rows():
        print(f"  {name:<11} {url:<24} {model}")
        print(f"  {'':<11} roles: {', '.join(served)}")
    print(f"  key         {KEY[:6]}... ({len(KEY)} chars, throwaway loopback key)")

    print("\n-- model servers --")
    up = True
    for name, host, port in SERVERS:
        found = models_on(host, port)
        if found is None:
            bad(f"{name}  {host}:{port}  "
                + probe_state(f"http://{host}:{port}/api/tags"))
            up = False
        else:
            ok(f"{name}  {host}:{port}  {', '.join(found) or 'no models'}")

    print("\n-- stack --")
    for name, url in (("litellm", f"{LITELLM}/health/liveliness"), ("openhands", AGENT)):
        if get(url, timeout=5) is not None:
            ok(f"{name:<10} {url}")
        else:
            bad(f"{name:<10} {url}  " + probe_state(url))

    print("\n-- routing --")
    data = get(f"{LITELLM}/v1/models", timeout=10,
               headers={"Authorization": f"Bearer {KEY}"})
    if data is None or not data.get("data"):
        bad(f"litellm is not answering /v1/models")
        return up
    served = {m["id"] for m in data["data"]}
    for role in ROLES:
        (ok if role in served else bad)(f"{role:<17} -> alias")
    # Print the model behind each alias: an alias can be served by a model that
    # cannot emit a tool call.
    print(f"  routing comes from {CONFIG_YML.relative_to(ROOT)}, generated from .env")
    return up

def config_rows():
    from config import ROLES as _roles, endpoint_of
    rows = []
    for letter in ("A", "B"):
        served = [r for r in _roles if endpoint_of(r, ENV) == letter]
        rows.append((f"endpoint {letter}",
                     ENV[f"ENDPOINT_{letter}_URL"],
                     ENV[f"ENDPOINT_{letter}_MODEL"],
                     served))
    return rows

def resolve_profile(role):
    data = agent_api("/api/agent-profiles")
    if not data:
        return None, None
    for p in data.get("profiles", []):
        if p.get("name") == role:
            return p["id"], p.get("llm_profile_ref")
    return None, None

def render_prompt(text, role, workdir, **extra):
    values = {"{{WORKDIR}}": workdir,
              "{{MODULE}}": WORKER_MODULE.get(role, ""),
              "{{ROLE}}": role or "",
              "{{ROOT}}": WORKDIR}
    values.update({"{{%s}}" % k: str(v) for k, v in extra.items()})
    for placeholder, value in values.items():
        text = text.replace(placeholder, value)
    return text

def scope_prompt(prompt, role, workdir):
    # Only a worker inside .worktrees/ is on its own branch. The tester works in
    # the demo project on main, and telling it otherwise sent it to a branch
    # that does not exist.
    if not role or "/.worktrees/" not in workdir:
        return prompt
    fragment = FRAGMENTS / "worktree-scope.md"
    if not fragment.exists():
        warn(f"missing {fragment.relative_to(ROOT)}; the worker is not told "
             "which branch it is on")
        return prompt
    header = render_prompt(fragment.read_text(), role, workdir).rstrip() + "\n\n"
    return f"{header}{prompt}"

def run_role(target, confirm=DEFAULT_CONFIRMATION, workdir=WORKDIR, started=None,
             finished=None, max_iterations=MAX_ITERATIONS, deadline=None,
             extra=None):
    if confirm not in CONFIRMATION:
        bad(f"unknown confirmation mode {confirm!r}; "
            f"pick one of {', '.join(CONFIRMATION)}")
        return None

    prompt, label, role = target, "custom prompt", None
    if target in ROLES:
        role = target
        # So {{WORKDIR}} means the same thing from the main checkout or a worktree.
        if workdir == WORKDIR:
            workdir = workdir_for(role)
        path = PROMPTS / f"{ROLES[role]}.md"
        if path.exists():
            prompt = scope_prompt(
                render_prompt(path.read_text(), role, workdir, **(extra or {})),
                role, workdir)
            label = f"prompts/{path.name}"
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
        "max_iterations": max_iterations,
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
    return wait_for(cid, started, finished, deadline)

def status_of(cid):
    return str((agent_api(f"/api/conversations/{cid}", timeout=30) or {})
               .get("execution_status", "?")).lower()

def nudge(cid, text, finished=None, deadline=None):
    """Send a follow-up turn to a conversation that has ended, and wait again.

    Small models often end a stage by pasting a file's content into a chat
    reply. OpenHands treats any plain reply as "done", so the stage finishes
    with nothing written. Re-prompting the same conversation keeps everything
    it already read and ran in context, so the retry costs one turn rather than
    a whole rerun.
    """
    sent = agent_api(f"/api/conversations/{cid}/events",
                     {"role": "user", "content": [{"type": "text", "text": text}],
                      "run": True}, timeout=30)
    if sent is None:
        bad(f"could not send a follow-up to {cid}")
        return None
    # The post returns before the loop restarts; without this the first poll
    # still reads the old "finished" and the wait returns at once.
    t = time.time()
    while status_of(cid) in DONE and time.time() - t < 30:
        time.sleep(2)
    return wait_for(cid, None, finished, deadline)

def wait_for(cid, started=None, finished=None, deadline=None):
    while True:
        state = str((agent_api(f"/api/conversations/{cid}", timeout=30) or {})
                    .get("execution_status", "?")).lower()
        if state in DONE:
            if finished is not None:
                finished["cid"] = cid
                finished["t1"] = time.time()
            (ok if state == "finished" else warn)(f"finished: {state}")
            return cid
        # Wall-clock cap: a thinking model on a memory-starved host can loop
        # read-then-plan forever. Stops the wait, not the agent - hence the
        # explicit conversation stop below.
        if deadline and time.time() > deadline:
            warn(f"hit the {int(deadline - started['t0']) if started else 0}s "
                 "budget, pausing the conversation")
            agent_api(f"/api/conversations/{cid}/pause", {}, timeout=30)
            if finished is not None:
                finished["cid"] = cid
                finished["t1"] = time.time()
            return cid
        time.sleep(5)

WORKTREES = ROOT / ".worktrees"

# Roles that work on the demo project, not the repo root. Without this the
# testing prompt resolved QUALITY.md one level above the project.
PROJECT_ROLES = {"coder-1", "coder-2", "tester", "docs"}

def workdir_for(role, base=WORKDIR):
    return f"{base}/{DEMO}" if role in PROJECT_ROLES else base

def git(*args, check=True):
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    if check and proc.returncode:
        bad(f"git {' '.join(args)} -> {out[:300]}")
    return proc.returncode, out

def make_worktree(worker):
    branch = f"agent/{worker}"
    path = WORKTREES / worker
    WORKTREES.mkdir(exist_ok=True)
    if path.exists():
        # Via git first: git on an untracked dir prints "is not a working tree",
        # which looks like a failure but only means a previous run cleaned up.
        if git("worktree", "remove", "--force", str(path), check=False)[0] == 0:
            ok(f"cleared the previous worktree for {worker}")
        else:
            import shutil
            shutil.rmtree(path, ignore_errors=True)
            git("worktree", "prune", check=False)
    # -B so a rerun starts clean. --relative-paths is required: an absolute
    # .git pointer does not resolve inside the container, so `git rev-parse`
    # failed there and no conversation was created.
    code, out = git("worktree", "add", "--relative-paths", "-B", branch, str(path))
    if code:
        return None
    ok(f"worktree {path.relative_to(ROOT)} on branch {branch}")
    return workdir_for(worker, f"{WORKDIR}/{WORKTREES.name}/{worker}")

def commit_worktree(worker, message=None):
    path = WORKTREES / worker
    if not path.exists():
        return 0, None
    git("-C", str(path), "add", "-A")
    staged = git("-C", str(path), "diff", "--cached", "--name-only", check=False)[1]
    if not staged:
        return 0, None
    files = len(staged.splitlines())
    msg = message or f"{worker}: agent output"
    # Unsigned on purpose: these are harness commits on throwaway agent/<role>
    # branches. Inheriting the user's commit.gpgsign meant a locked SSH signing
    # agent (1Password) failed every commit, and the stage then integrated the
    # untouched stubs instead of the agent's work.
    code, out = git("-c", "commit.gpgsign=false", "-C", str(path),
                    "commit", "-m", msg)
    if code:
        bad(f"{worker}: commit failed -> {out[:200]}")
        return 0, None
    ok(f"{worker}: committed {files} file(s) on agent/{worker}")
    sha = git("-C", str(path), "rev-parse", "--short", "HEAD", check=False)[1]
    return files, sha

def integrate(worker, paths):
    """Take `paths` from a worker's branch into the main checkout.

    A full `git merge` is the obvious way to do this and it is what this used to
    do, but it refuses to run whenever the main checkout has any uncommitted
    change at all -- and this repo has a lot, none of it related to the agents.
    It also merges whatever else the branch happens to touch, so one worker can
    drag in the other worker's files.

    Checking out just the stage's own paths keeps the integration scoped to what
    the stage promised and works on a dirty tree. The branch and its commit
    stay put, so the diff is still there to review.
    """
    if not paths:
        return []
    taken = []
    for relpath in paths:
        if git("cat-file", "-e", f"agent/{worker}:{relpath}", check=False)[0] != 0:
            warn(f"{worker}: {relpath} is not on the branch, skipping")
            continue
        code, out = git("checkout", f"agent/{worker}", "--", relpath, check=False)
        if code:
            bad(f"{worker}: could not take {relpath} -> {out[:200]}")
            continue
        taken.append(relpath)
    if taken:
        ok(f"{worker}: took {len(taken)} file(s) from agent/{worker}: "
           + ", ".join(taken))
    return taken


def drop_worktree(worker, merge=True):
    path = WORKTREES / worker
    if not path.exists():
        return False
    commit_worktree(worker)
    if merge:
        # Diff against the merge base, not HEAD: once an earlier worker has
        # merged, "diff HEAD agent/<w>" also lists files this worker never
        # touched, which over-reports what it changed.
        base = git("merge-base", "HEAD", f"agent/{worker}", check=False)[1].split()
        changed = git("diff", "--name-only", base[0] if base else "HEAD",
                      f"agent/{worker}")[1]
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

def run_workers(workers, confirm=DEFAULT_CONFIRMATION,
                max_iterations=MAX_ITERATIONS, budget=None, reset=()):
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

    # file_editor's create command refuses to overwrite, so a leftover stub makes
    # the worker's write fail. Removing the worker's own target inside its own
    # worktree means the write always lands and every rerun starts identically.
    # Only the worker's own module goes: deleting the other worker's file would
    # put a spurious deletion in this branch and collide on merge.
    for w in workers:
        targets = reset.get(w, []) if isinstance(reset, dict) else list(reset)
        for relpath in targets:
            stale = WORKTREES / w / relpath
            if stale.exists():
                stale.unlink()
                ok(f"{w}: removed stale {relpath} so create can write it")

    marks = {w: {"started": {}, "finished": {}} for w in workers}
    print(f"\n-- {len(workers)} workers in parallel --")
    t_start = time.time()
    # Per worker, not shared: they start together, so a shared deadline would
    # cut the first one short for no reason.
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(workers)) as pool:
        futures = {
            w: pool.submit(run_role, w, confirm, workdirs[w],
                           marks[w]["started"], marks[w]["finished"],
                           max_iterations,
                           t_start + budget if budget else None)
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
    if any(a in ("-h", "--help", "help") for a in args):
        print((__doc__ or "").strip())
        return 0

    check_only = "--check" in args
    want_run = "--run" in args or not check_only

    confirm, rest = DEFAULT_CONFIRMATION, []
    workers = None
    do_merge = False
    max_iterations = MAX_ITERATIONS
    # STAGE_BUDGET=0 in .env means no cap; the flag still wins.
    budget = STAGE_BUDGET or None
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
        elif a in ("--budget", "--max-iterations") and i + 1 < len(args):
            try:
                value = int(args[i + 1])
            except ValueError:
                bad(f"--{a.lstrip('-')} needs a whole number of seconds/turns")
                return 1
            budget, max_iterations = (value, max_iterations) if a == "--budget" \
                else (budget, value)
            i += 2
        elif a.startswith("--budget=") or a.startswith("--max-iterations="):
            flag, _, raw = a.partition("=")
            try:
                value = int(raw)
            except ValueError:
                bad(f"{flag} needs a whole number of seconds/turns")
                return 1
            budget, max_iterations = (value, max_iterations) if flag == "--budget" \
                else (budget, value)
            i += 1
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
        result = run_workers(workers, confirm, max_iterations, budget)
        if not result.get("conversations"):
            return 1
        failed = [w for w, cid in result["conversations"].items() if not cid]
        if do_merge:
            failed += [w for w in workers if not drop_worktree(w)]
        return 1 if failed else 0
    run_role(rest[0] if rest else "architect", confirm=confirm,
             max_iterations=max_iterations,
             deadline=time.time() + budget if budget else None)
    return 0

if __name__ == "__main__":
    sys.exit(main())
