#!/usr/bin/env python3
"""Run the six-role OpenHands pipeline against the two local endpoints.

    python3 scripts/pipeline.py                     # all six stages
    python3 scripts/pipeline.py --from tester       # resume at a stage
    python3 scripts/pipeline.py --check             # preflight only
    python3 scripts/pipeline.py --compare RUN_A RUN_B
"""

import json
import re
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

from config import ROLES, ROOT, WORKER_MODULE, endpoint_of, sync

WORKDIR = "/opt/project"                 # the repo, as mounted in the container
DEMO = "workspace/demo-project"
AGENT = "http://localhost:8000"
API_KEY = ROOT / "openhands" / "state" / "agent-canvas" / "api-key.txt"
RUNS = ROOT / "artifacts" / "runs"
DONE = {"finished", "error", "stopped", "paused", "idle", "stuck"}
NUDGES = 2

# What each stage must leave behind; `words` must appear in the first file.
STAGES = [
    {"role": "architect", "fr": "FR1",
     "files": ["docs/components.md", "docs/api.md", "docs/deployment.md",
               "docs/decisions.md", "docs/handoff.md"]},
    {"role": "techlead", "fr": "FR2",
     "files": ["tickets/list.md"], "tickets": 3},
    {"role": "coders", "fr": "FR3", "workers": ["coder-1", "coder-2"],
     "files": [f"{DEMO}/src/todoapp/storage.py", f"{DEMO}/src/todoapp/server.py"]},
    {"role": "tester", "fr": "FR4",
     "files": [f"{DEMO}/QUALITY.md"], "words": ["test result", "limitation"]},
    {"role": "docs", "fr": "FR5",
     "files": [f"{DEMO}/README.md"],
     "words": ["setup", "usage", "runbook", "troubleshoot"]},
    {"role": "deploy-validator", "fr": "FR6",
     "files": ["docs/deployment-validation.md"], "words": ["checklist"],
     "precommand": "./docker/validate.sh"},
]


def say(ok, msg):
    print(f"  [{'ok' if ok else 'FAIL'}] {msg}")


def api(path, payload=None, timeout=30):
    req = urllib.request.Request(
        AGENT + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json",
                 "X-Session-API-Key": API_KEY.read_text().strip()})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body) if body else {}


def reachable(url):
    try:
        urllib.request.urlopen(url, timeout=5)
        return True
    except Exception:
        return False


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


# ---------------------------------------------------------------- preflight

def preflight(env):
    for letter in ("A", "B"):
        url = f"http://127.0.0.1:{env[f'ENDPOINT_{letter}_PORT']}/api/tags"
        say(reachable(url), f"endpoint {letter} {env[f'ENDPOINT_{letter}_MODEL']} "
            f"-> {env[f'ENDPOINT_{letter}_ROLES']}")
        if not reachable(url):
            return False
    subprocess.run(["docker", "compose", "up", "-d"], cwd=ROOT, capture_output=True)
    for name, url in (("litellm", "http://localhost:4000/health/liveliness"),
                      ("openhands", AGENT)):
        for _ in range(60):
            if reachable(url) and (name == "litellm" or API_KEY.exists()):
                break
            time.sleep(2)
        else:
            say(False, f"{name} did not start: docker compose logs {name}")
            return False
        say(True, f"{name} up")
    return True


# ------------------------------------------------------------- one agent run

def prompt_for(role, workdir, extra=None):
    text = (ROOT / "prompts" / f"{ROLES[role]}.md").read_text()
    values = {"WORKDIR": workdir, "MODULE": WORKER_MODULE.get(role, ""), **(extra or {})}
    for key, value in values.items():
        text = text.replace("{{%s}}" % key, value)
    return text


def profile_id(role):
    profiles = api("/api/agent-profiles")["profiles"]
    return next(p["id"] for p in profiles if p["name"] == role)


def wait(cid, deadline):
    while time.time() < deadline:
        if api(f"/api/conversations/{cid}").get("execution_status") in DONE:
            return
        time.sleep(5)
    print(f"  [warn] {cid} hit the stage budget, pausing it")
    api(f"/api/conversations/{cid}/pause", {})


def run_agent(role, workdir, env, extra=None):
    conv = api("/api/conversations", {
        "agent_profile_id": profile_id(role),
        "workspace": {"working_dir": workdir, "kind": "LocalWorkspace"},
        "initial_message": {"role": "user", "run": True, "content": [
            {"type": "text", "text": prompt_for(role, workdir, extra)}]},
        "max_iterations": int(env["MAX_ITERATIONS"]),
        # NFR1: never | risky (ask before risky commands) | always
        "confirmation_policy": {"kind": {"never": "NeverConfirm", "risky": "ConfirmRisky",
                                         "always": "AlwaysConfirm"}[env["CONFIRMATION"]]},
    })
    cid = conv.get("conversation_id") or conv["id"]
    print(f"  {role}: conversation {cid}  (watch at {AGENT})")
    wait(cid, time.time() + int(env["STAGE_BUDGET"]))
    return cid


def nudge(cid, missing, env):
    """Small models often paste a file into chat instead of writing it."""
    paths = "\n".join(f"- {WORKDIR}/{p}" for p in missing)
    api(f"/api/conversations/{cid}/events", {"role": "user", "run": True, "content": [{
        "type": "text",
        "text": "These files still do not exist:\n\n" + paths + "\n\nCall `file_editor` "
                "with `command` `create`, `path` set to the absolute path and the whole "
                "file as `file_text`. One file per call."}]})
    time.sleep(10)
    wait(cid, time.time() + int(env["STAGE_BUDGET"]))


# ------------------------------------------------------- the parallel coders

def worktree(worker):
    path = ROOT / ".worktrees" / worker
    git("worktree", "remove", "--force", str(path))
    # --relative-paths so the worktree's .git pointer also resolves in the container.
    git("worktree", "add", "--relative-paths", "-B", f"agent/{worker}", str(path))
    # file_editor `create` refuses to overwrite, so remove the stub first.
    (path / DEMO / "src" / "todoapp" / WORKER_MODULE[worker]).unlink(missing_ok=True)
    return f"{WORKDIR}/.worktrees/{worker}/{DEMO}"


def collect(worker):
    """Commit the worker's branch, then take only its own module into main."""
    path = ROOT / ".worktrees" / worker
    module = f"{DEMO}/src/todoapp/{WORKER_MODULE[worker]}"
    wrote = (path / module).exists()
    git("-C", str(path), "add", "-A")
    # Unsigned: these are throwaway harness commits, not the user's. A worker
    # that writes the same file as last time leaves nothing to commit; that is fine.
    git("-c", "commit.gpgsign=false", "-C", str(path), "commit", "-qm", f"{worker}: agent output")
    if wrote:
        git("checkout", f"agent/{worker}", "--", module)
    git("worktree", "remove", "--force", str(path))
    say(wrote, f"{worker}: wrote {module} on agent/{worker}, taken into main")
    return wrote


def run_coders(stage, env):
    dirs = {w: worktree(w) for w in stage["workers"]}
    threads = [threading.Thread(target=run_agent, args=(w, dirs[w], env))
               for w in stage["workers"]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return all([collect(w) for w in stage["workers"]])


# ------------------------------------------------------------------ a stage

def missing_files(stage):
    return [p for p in stage["files"]
            if not (ROOT / p).exists() or (ROOT / p).stat().st_size < 100]


def verify(stage):
    passed = True
    for p in stage["files"]:
        f = ROOT / p
        good = f.exists() and f.stat().st_size >= 100
        say(good, f"{p}: {f.stat().st_size if f.exists() else 0} bytes")
        passed &= good
    if stage.get("words") and not missing_files(stage):
        text = (ROOT / stage["files"][0]).read_text().lower()
        absent = [w for w in stage["words"] if w not in text]
        say(not absent, "covers " + ", ".join(stage["words"])
            + (f" (missing: {', '.join(absent)})" if absent else ""))
        passed &= not absent
    if stage.get("tickets"):
        n = len([p for p in (ROOT / "tickets").glob("*.md")
                 if p.name not in ("list.md", "README.md")])
        say(n >= stage["tickets"], f"{n} ticket files")
        passed &= n >= stage["tickets"]
    if stage.get("workers"):
        stubs = [p for p in stage["files"] if (ROOT / p).exists()
                 and "NotImplementedError" in (ROOT / p).read_text()]
        say(not stubs, "no NotImplementedError stubs left")
        passed &= not stubs
    return passed


def run_stage(stage, env):
    role = stage["role"]
    route = endpoint_of(stage.get("workers", [role])[0], env)
    print(f"\n== {stage['fr']} {role}  (endpoint {route}: {env[f'ENDPOINT_{route}_MODEL']})")
    t0 = time.time()
    if stage.get("workers"):
        wrote = run_coders(stage, env)
    else:
        # Outputs from the last run would make `create` fail, or pass unread.
        old = [ROOT / p for p in stage["files"]]
        if stage.get("tickets"):
            old += [p for p in (ROOT / "tickets").glob("*.md") if p.name != "README.md"]
        for f in old:
            f.unlink(missing_ok=True)
        extra = {}
        if stage.get("precommand"):
            # Run on the host, where docker is; the agent reports on the real output.
            out = subprocess.run(stage["precommand"], cwd=ROOT, shell=True,
                                 capture_output=True, text=True)
            extra["COMMAND_OUTPUT"] = "\n".join(
                re.sub(r"\x1b\[[0-9;]*m", "", out.stdout + out.stderr).splitlines()[-60:])
        workdir = f"{WORKDIR}/{DEMO}" if role in ("tester", "docs") else WORKDIR
        cid = run_agent(role, workdir, env, extra)
        for _ in range(NUDGES):
            missing = missing_files(stage)
            if not missing:
                break
            print(f"  [warn] {role} did not write {', '.join(missing)}; asking again")
            nudge(cid, missing, env)
    passed = verify(stage) and (wrote if stage.get("workers") else True)
    return {"role": role, "fr": stage["fr"], "passed": passed,
            "seconds": round(time.time() - t0),
            "files": [p for p in stage["files"] if (ROOT / p).exists()]}


# ------------------------------------------------------------- compare runs

def compare(a, b):
    ra, rb = (json.loads((RUNS / r / "run.json").read_text()) for r in (a, b))
    same = True
    print(f"{'stage':<18}{a:>18}{b:>18}")
    for sa, sb in zip(ra["stages"], rb["stages"]):
        marks = ["pass" if s["passed"] else "FAIL" for s in (sa, sb)]
        same &= sa["role"] == sb["role"] and marks[0] == marks[1] and sa.get("files") == sb.get("files")
        print(f"{sa['role']:<18}{marks[0]:>18}{marks[1]:>18}")
    same &= len(ra["stages"]) == len(rb["stages"])
    print("comparable: same stages, verdicts and files" if same else "NOT comparable")
    return 0 if same else 1


def main():
    args = sys.argv[1:]
    if args[:1] == ["--compare"]:
        return compare(args[1], args[2])
    env = sync()
    if not preflight(env):
        return 1
    if "--check" in args:
        return 0
    stages = STAGES
    if "--from" in args:
        start = args[args.index("--from") + 1]
        stages = STAGES[[s["role"] for s in STAGES].index(start):]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = []
    for stage in stages:
        results.append(run_stage(stage, env))
        if not results[-1]["passed"]:
            print(f"\nstopping: {stage['role']} did not deliver; later stages depend on it")
            break

    run_dir = RUNS / stamp
    run_dir.mkdir(parents=True)
    routing = {l: {"model": env[f"ENDPOINT_{l}_MODEL"], "roles": env[f"ENDPOINT_{l}_ROLES"]}
               for l in ("A", "B")}
    (run_dir / "run.json").write_text(json.dumps(
        {"started": stamp, "routing": routing, "stages": results}, indent=2) + "\n")

    print("\n== summary")
    for r in results:
        print(f"  {r['fr']}  {r['role']:<17} {r['seconds']:>5}s  "
              f"{'verified' if r['passed'] else 'FAILED'}")
    print(f"  record: artifacts/runs/{stamp}/run.json")
    return 0 if all(r["passed"] for r in results) and len(results) == len(stages) else 1


if __name__ == "__main__":
    sys.exit(main())
