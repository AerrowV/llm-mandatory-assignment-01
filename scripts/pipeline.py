#!/usr/bin/env python3
"""Run the six-role OpenHands pipeline against the two local endpoints.

    python3 scripts/pipeline.py                     # all six stages
    python3 scripts/pipeline.py --from tester       # resume at a stage
    python3 scripts/pipeline.py --check             # preflight only
    python3 scripts/pipeline.py --compare RUN_A RUN_B

The roles work as a team: each one's final reply is posted to a shared team
chat that every later role reads, and failing tests go back to the coders for
a fix round before the tester checks again.
"""

import json
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

from config import PACKAGE, ROLES, ROOT, WORKER_MODULE, WORKER_TESTS, endpoint_of, sync

WORKDIR = "/opt/project"                 # the repo, as mounted in the container
DEMO = "workspace/demo-project"
AGENT = "http://localhost:8000"
API_KEY = ROOT / "openhands" / "state" / "agent-canvas" / "api-key.txt"
RUNS = ROOT / "artifacts" / "runs"
DONE = {"finished", "error", "stopped", "paused", "idle", "stuck"}
NUDGES = 2
FIX_ROUNDS = 2
TEAM = []          # (role, message): the team chat, in order
FIX = {}           # worker -> its failing tests, while a fix round is running

# What each stage must leave behind; `words` must appear in the first file.
STAGES = [
    {"role": "architect", "fr": "FR1",
     "files": ["docs/components.md", "docs/api.md", "docs/deployment.md",
               "docs/decisions.md", "docs/handoff.md"]},
    {"role": "techlead", "fr": "FR2",
     "files": ["tickets/list.md", "tickets/001-ops.md", "tickets/002-cli.md",
               "tickets/003-testing.md"]},
    {"role": "coders", "fr": "FR3", "workers": ["coder-1", "coder-2"],
     "files": [f"{DEMO}/src/{PACKAGE}/{WORKER_MODULE[w]}" for w in ("coder-1", "coder-2")]},
    {"role": "tester", "fr": "FR4",
     "files": [f"{DEMO}/QUALITY.md"], "words": ["test result", "limitation"],
     "precommand": f"cd {DEMO} && python3 -m unittest discover -s tests -v 2>&1; "
                   "python3 -m compileall -q src && echo 'static check (compileall): ok'"},
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

def fill(name, **values):
    """Every text an agent sees is a file in prompts/; this fills its {{KEYS}}."""
    text = (ROOT / "prompts" / f"{name}.md").read_text()
    for key, value in values.items():
        text = text.replace("{{%s}}" % key, value)
    return text


def prompt_for(role, workdir, extra=None):
    chat = "\n".join(f"- **{who}**: {msg}" for who, msg in TEAM[-4:]) or "(no messages yet)"
    module = WORKER_MODULE.get(role, "")
    text = fill(ROLES[role], WORKDIR=workdir, MODULE=module, **(extra or {}))
    if role in FIX:
        text += "\n\n" + fill("shared/fix-round", WORKDIR=workdir, MODULE=module,
                                FAILURES=FIX[role])
    return text + "\n\n" + fill("shared/team-chat", CHAT=chat)


def profile_id(role):
    profiles = api("/api/agent-profiles")["profiles"]
    return next(p["id"] for p in profiles if p["name"] == role)


def wait(cid, deadline):
    while time.time() < deadline:
        if api(f"/api/conversations/{cid}").get("execution_status") in DONE:
            return
        time.sleep(2)
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


def listen(role, cid):
    """Post the agent's final reply to the team chat."""
    try:
        reply = api(f"/api/conversations/{cid}/agent_final_response").get("response", "")
    except Exception:
        reply = ""
    reply = " ".join(reply.split())[:300]
    # A tool call written as text is a failure, not a message; posting it would
    # teach the next role to do the same.
    if reply and '{"name"' not in reply:
        TEAM.append((role, reply))
        print(f"  {role} says: {reply[:160]}")


def nudge(cid, missing, env, text=None, note=""):
    """Small models often paste a file into chat instead of writing it."""
    paths = "\n".join(f"- {WORKDIR}/{p}" for p in missing)
    api(f"/api/conversations/{cid}/events", {"role": "user", "run": True, "content": [{
        "type": "text",
        "text": text or fill("shared/missing-files", PATHS=paths, NOTE=note)}]})
    time.sleep(3)
    wait(cid, time.time() + int(env["STAGE_BUDGET"]))


# ------------------------------------------------------- the parallel coders

def worktree(worker):
    path = ROOT / ".worktrees" / worker
    git("worktree", "remove", "--force", str(path))
    # An interrupted run can leave the folder behind, and `worktree add` refuses
    # an existing path - the worker then runs in an empty directory.
    shutil.rmtree(path, ignore_errors=True)
    git("worktree", "prune")
    # --relative-paths so the worktree's .git pointer also resolves in the container.
    made = git("worktree", "add", "--relative-paths", "-B", f"agent/{worker}", str(path))
    if made.returncode:
        raise SystemExit(f"git worktree add failed for {worker}: {made.stderr.strip()}")
    module = path / DEMO / "src" / PACKAGE / WORKER_MODULE[worker]
    if FIX:  # in a fix round the worker starts from its own last attempt
        module.with_suffix(".py.prev").write_text(
            (ROOT / DEMO / "src" / PACKAGE / WORKER_MODULE[worker]).read_text())
    # file_editor `create` refuses to overwrite, so remove the file first.
    module.unlink(missing_ok=True)
    return f"{WORKDIR}/.worktrees/{worker}/{DEMO}"


def collect(worker):
    """Commit the worker's branch, then take only its own module into main."""
    path = ROOT / ".worktrees" / worker
    module = f"{DEMO}/src/{PACKAGE}/{WORKER_MODULE[worker]}"
    wrote = (path / module).exists()
    (path / f"{module}.prev").unlink(missing_ok=True)
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
    # In a fix round only the coders whose own tests fail go back to work.
    workers = [w for w in stage["workers"] if w in FIX] or stage["workers"]
    dirs = {w: worktree(w) for w in workers}
    cids = {}

    def work(w):
        cids[w] = run_agent(w, dirs[w], env)
        module = f".worktrees/{w}/{DEMO}/src/{PACKAGE}/{WORKER_MODULE[w]}"
        for _ in range(NUDGES):
            if (ROOT / module).exists():
                break
            print(f"  [warn] {w} did not write its module; asking again")
            # Coders must read the spec (and their last attempt) before writing,
            # or they write generic code from memory.
            prev = (f"\n   Then `view` `{dirs[w]}/src/{PACKAGE}/{WORKER_MODULE[w]}.prev`, "
                    "your previous version." if w in FIX else "")
            nudge(cids[w], [module], env, fill(
                "shared/missing-module", PATH=f"{WORKDIR}/{module}", WORKDIR=dirs[w], PREV=prev))

    threads = [threading.Thread(target=work, args=(w,)) for w in workers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for w in workers:
        listen(w, cids[w])
    return all([collect(w) for w in workers])


# ------------------------------------------------------------------ a stage

def missing_files(stage):
    return [p for p in stage["files"]
            if not (ROOT / p).exists() or (ROOT / p).stat().st_size < 50]


def missing_words(stage):
    """Required terms the stage's first file does not contain yet."""
    f = ROOT / stage["files"][0]
    if not stage.get("words") or not f.exists():
        return []
    text = f.read_text().lower()
    return [w for w in stage["words"] if w not in text]


def verify(stage):
    passed = True
    for p in stage["files"]:
        f = ROOT / p
        good = f.exists() and f.stat().st_size >= 50
        say(good, f"{p}: {f.stat().st_size if f.exists() else 0} bytes")
        passed &= good
    if stage.get("words") and not missing_files(stage):
        text = (ROOT / stage["files"][0]).read_text().lower()
        absent = [w for w in stage["words"] if w not in text]
        say(not absent, "covers " + ", ".join(stage["words"])
            + (f" (missing: {', '.join(absent)})" if absent else ""))
        passed &= not absent
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
        for p in stage["files"]:
            (ROOT / p).unlink(missing_ok=True)
        extra = {}
        if stage.get("precommand"):
            # Run on the host (docker, real tests); the agent reports on the real output.
            out = subprocess.run(stage["precommand"], cwd=ROOT, shell=True,
                                 capture_output=True, text=True)
            extra["COMMAND_OUTPUT"] = "\n".join(
                re.sub(r"\x1b\[[0-9;]*m", "", out.stdout + out.stderr).splitlines()[-60:])
        workdir = f"{WORKDIR}/{DEMO}" if role in ("tester", "docs") else WORKDIR
        cid = run_agent(role, workdir, env, extra)
        for _ in range(NUDGES):
            missing, absent = missing_files(stage), missing_words(stage)
            if absent and not missing:  # written, but stopped before the end
                missing = stage["files"][:1]
            if not missing:
                break
            print(f"  [warn] {role} did not write {', '.join(missing)}"
                  + (f" (missing: {', '.join(absent)})" if absent else "") + "; asking again")
            for m in missing:  # an incomplete file would make `create` refuse
                (ROOT / m).unlink(missing_ok=True)
            note = (f"It must cover all of: {', '.join(stage['words'])}."
                    if absent else "")
            nudge(cid, missing, env, note=note)
        listen(role, cid)
    passed = verify(stage) and (wrote if stage.get("workers") else True)
    return {"role": role, "fr": stage["fr"], "passed": passed,
            "seconds": round(time.time() - t0),
            "files": [p for p in stage["files"] if (ROOT / p).exists()]}


# ---------------------------------------------------------------- fix loop

def run_tests():
    """Run the demo tests on the host.

    Returns (tests passing, summary or None, {test file: [failing test names]}).
    """
    out = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                         cwd=ROOT / DEMO, capture_output=True, text=True, timeout=120)
    lines = out.stderr.splitlines()
    ran = int(next((l.split()[1] for l in lines if l.startswith("Ran ")), 0))
    bad = sum(int(n) for n in re.findall(r"(?:failures|errors)=(\d+)", lines[-1] if lines else ""))
    if out.returncode == 0:
        return ran, None, {}
    failing = {}
    for l in lines:
        m = re.match(r"(FAIL|ERROR): (\w+) \(([\w.]+)\)", l)
        if m:
            # "ERROR: test_cli (unittest.loader._FailedTest.test_cli)" = the file did not import
            module = m[2] if m[3].startswith("unittest.") else m[3].split(".")[0]
            failing.setdefault(module, []).append(f"- {m[1]}: {m[2]}")
    # Test names only: a long failure dump pushes the 8b model into answering in text.
    summary = "\n".join(n for names in failing.values() for n in names[:8]) + "\n" + lines[-1]
    return ran - bad, summary, failing


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
    global FIX
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
    by_role = {s["role"]: s for s in STAGES}
    for stage in stages:
        results.append(run_stage(stage, env))
        if not results[-1]["passed"]:
            print(f"\nstopping: {stage['role']} did not deliver; later stages depend on it")
            break
        # The team works it out: failing tests go back to the coders, then the
        # tester checks again.
        for round_ in range(1, FIX_ROUNDS + 1 if stage["role"] == "tester" else 1):
            passing, failures, failing = run_tests()
            if not failures:
                print(f"  all {passing} tests pass - no fix round needed")
                break
            # Each coder gets only its own failing tests; failures elsewhere go to both.
            FIX = {w: "\n".join(failing[t]) + "\n" for w, t in WORKER_TESTS.items() if t in failing}
            if not FIX:
                FIX = {w: failures for w in WORKER_TESTS}
            print(f"\n== fix round {round_}: {passing} tests pass, back to {', '.join(FIX)}")
            modules = [ROOT / p for p in by_role["coders"]["files"]]
            before = {m: m.read_text() for m in modules}
            TEAM.append(("test run", f"{failures.splitlines()[-1]} - {', '.join(FIX)}, please fix."))
            results.append(run_stage(by_role["coders"], env))
            results[-1]["role"] += f" (fix {round_})"
            FIX = {}
            now, _, _ = run_tests()
            if now <= passing:
                # Keep a fix only if it helps; a weaker attempt goes back out.
                for m, text in before.items():
                    m.write_text(text)
                print(f"  fix rejected: {now} tests pass, not more than {passing}; previous code kept")
                TEAM.append(("test run", f"Fix rejected ({now} passing, before {passing}); "
                                         "previous code kept."))
                continue
            print(f"  fix kept: {now} tests pass, up from {passing}")
            TEAM.append(("test run", f"Fix kept: {now} tests pass, up from {passing}."))
            results.append(run_stage(by_role["tester"], env))
            results[-1]["role"] += f" (fix {round_})"

    run_dir = RUNS / stamp
    run_dir.mkdir(parents=True)
    routing = {l: {"model": env[f"ENDPOINT_{l}_MODEL"], "roles": env[f"ENDPOINT_{l}_ROLES"]}
               for l in ("A", "B")}
    (run_dir / "run.json").write_text(json.dumps(
        {"started": stamp, "routing": routing, "stages": results}, indent=2) + "\n")
    (run_dir / "team-chat.md").write_text(
        "# Team chat\n\n" + "\n\n".join(f"**{who}**: {msg}" for who, msg in TEAM) + "\n")

    print("\n== summary")
    for r in results:
        print(f"  {r['fr']}  {r['role']:<17} {r['seconds']:>5}s  "
              f"{'verified' if r['passed'] else 'FAILED'}")
    print(f"  record: artifacts/runs/{stamp}/run.json, team-chat.md")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
