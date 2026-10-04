#!/usr/bin/env python3
"""Run the six-stage pipeline: architect, techlead, coders, tester, docs, deploy.

    python3 scripts/pipeline.py --stages coder-1 --budget 1500
    python3 scripts/pipeline.py --check
    python3 scripts/pipeline.py --compare RUN_A RUN_B
"""

import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import WORKER_MODULE, route_of
from agent import (  # noqa: E402  the orchestrator reuses the single implementation
    CONFIRMATION,
    DEFAULT_CONFIRMATION,
    MAX_ITERATIONS,
    ROLES,
    ROOT,
    STAGE_BUDGET,
    bad,
    commit_worktree,
    config_rows,
    drop_worktree,
    git,
    integrate,
    nudge,
    ok,
    resolve_profile,
    run_role,
    run_workers,
    show_state,
    start_stack,
    warn,
    workdir_for,
    WORKDIR,
)

RUNS = ROOT / "artifacts" / "runs"
BOLD, RESET = "\033[1m", "\033[0m"

# What each stage must leave behind. `min_bytes` is deliberately low: the point
# is to catch a file that was never written or written empty, not to grade prose.
# A stage that writes 40 bytes of narrative fails here, which is the whole point.
STAGES = [
    {
        "role": "architect",
        "title": "Architecture",
        "fr": "FR1",
        "expect": [
            "docs/components.md",
            "docs/api.md",
            "docs/deployment.md",
            "docs/decisions.md",
            "docs/handoff.md",
        ],
        "min_bytes": 200,
        # Otherwise files left by an earlier run satisfy the check untouched.
        "reset": ["docs/components.md", "docs/api.md", "docs/deployment.md",
                  "docs/decisions.md", "docs/handoff.md"],
    },
    {
        "role": "techlead",
        "title": "Tech lead",
        "fr": "FR2",
        "expect": ["tickets/list.md"],
        "min_bytes": 100,
        "reset": ["tickets/list.md", "tickets/001-storage.md",
                  "tickets/002-server.md", "tickets/003-testing.md"],
        # One ticket per task, so the count is the check rather than a fixed
        # list of filenames the agent has to guess. README.md is excluded: it
        # predates the pipeline and counting it would inflate the total.
        "expect_glob": [{"pattern": "tickets/*.md", "min": 3,
                         "exclude": ["tickets/list.md", "tickets/README.md"]}],
    },
    {
        "role": "coder-1",
        "role2": "coder-2",
        "title": "Implementation, two workers in parallel",
        "fr": "FR3",
        "parallel": ["coder-1", "coder-2"],
        "expect": [
            "workspace/demo-project/src/todoapp/storage.py",
            "workspace/demo-project/src/todoapp/server.py",
        ],
        "min_bytes": 400,
        # A stub is not an implementation: stops FR3 being reported met on a
        # file full of NotImplementedError.
        "forbid": ["NotImplementedError"],
        # Deleted inside each worker's worktree before the agent starts, because
        # file_editor's create refuses to overwrite and would fail on the stub.
        "reset": ["workspace/demo-project/src/todoapp/storage.py",
                  "workspace/demo-project/src/todoapp/server.py"],
    },
    {
        "role": "tester",
        "title": "Testing and quality",
        "fr": "FR4",
        # tests/test_integration.py is asked for but not required: llama3.1:8b
        # emits a long code file as JSON text instead of a tool call, even
        # after two follow-ups. The suite still runs and QUALITY.md reports it.
        "expect": ["workspace/demo-project/QUALITY.md"],
        "min_bytes": 300,
        "reset": ["workspace/demo-project/QUALITY.md",
                  "workspace/demo-project/tests/test_integration.py"],
        # The prompt promises a real result line, not a summary of one.
        "require": [{"file": "workspace/demo-project/QUALITY.md",
                     "terms": ["test result", "limitation"]}],
    },
    {
        "role": "docs",
        "title": "Documentation",
        "fr": "FR5",
        # The demo project's README, written from TASK.md and run.py. The repo's
        # own README is hand-written; a 3b model rewriting it invented commands.
        "expect": ["workspace/demo-project/README.md"],
        "min_bytes": 500,
        "require": [{"file": "workspace/demo-project/README.md",
                     "terms": ["setup", "usage", "runbook", "troubleshoot"]}],
        # file_editor create refuses to overwrite; README.md is tracked, so git
        # restores the original.
        "reset": ["workspace/demo-project/README.md"],
    },
    {
        "role": "deploy-validator",
        "title": "Deployment validation",
        "fr": "FR6",
        "expect": ["docs/deployment-validation.md"],
        # Run by the harness on the host, where docker is; the agent writes the
        # report from the real output instead of being trusted to run it. Left
        # to itself, llama3.1:8b skipped the script and reported invented passes.
        "precommand": ["./docker/validate.sh"],
        "min_bytes": 300,
        "reset": ["docs/deployment-validation.md"],
        "require": [{"file": "docs/deployment-validation.md",
                     "terms": ["checklist"]}],
    },
]

# --------------------------------------------------------------- utilities ----

def rel(path):
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)

def brief1(msg):
    print(f"\n{BOLD}== {msg}{RESET}")

def count_glob(spec):
    exclude = set(spec.get("exclude", []))
    found = [rel(p) for p in ROOT.glob(spec["pattern"])
             if p.is_file() and rel(p) not in exclude]
    return len(found), sorted(found)

def snapshot(paths):
    out = {}
    for p in paths:
        f = ROOT / p
        out[p] = f.stat().st_size if f.exists() else 0
    return out

def verify(stage, before):
    lines, passed = [], True

    for relpath in stage["expect"]:
        f = ROOT / relpath
        if not f.exists():
            bad(f"{relpath}: never written")
            passed = False
            continue
        size = f.stat().st_size
        was = before.get(relpath)
        floor = stage.get("min_bytes", 200)
        if size < floor:
            bad(f"{relpath}: {size} bytes, below the {floor}-byte floor "
                + (f"(was {was})" if was is not None else ""))
            passed = False
            continue
        delta = f", +{size - was} bytes" if was is not None and size != was else ""
        ok(f"{relpath}: {size} bytes{delta}")

    for spec in stage.get("expect_glob", []):
        n, names = count_glob(spec)
        if n < spec["min"]:
            bad(f"{spec['pattern']}: {n} file(s), need at least {spec['min']}")
            passed = False
        else:
            ok(f"{spec['pattern']}: {n} file(s) >= {spec['min']}")
        lines.append(f"{spec['pattern']}: {n} files: " + ", ".join(names[:12]))

    for needle in stage.get("forbid", []):
        hits = []
        for relpath in stage["expect"]:
            f = ROOT / relpath
            if f.exists() and needle in f.read_text(errors="replace"):
                hits.append(relpath)
        if hits:
            bad(f"{needle!r} still in " + ", ".join(hits) + " - that is a stub, "
                "not an implementation")
            passed = False
        else:
            ok(f"no {needle!r} left in the implementation")

    # Size alone is not evidence of content: an untouched 882-byte project plan
    # satisfies a 500-byte floor. `require` names terms the prompt actually
    # promised, matched case-insensitively.
    for spec in stage.get("require", []):
        relpath, terms = spec["file"], [t.lower() for t in spec["terms"]]
        f = ROOT / relpath
        if not f.exists():
            continue
        text = f.read_text(errors="replace").lower()
        missing = [t for t in terms if t not in text]
        if missing:
            bad(f"{relpath}: missing required content: {', '.join(missing)}")
            passed = False
        else:
            ok(f"{relpath}: covers {' + '.join(spec['terms'])}")

    return passed, lines

def copy_artifacts(stage, dest):
    kept = []
    sources = [ROOT / p for p in stage["expect"]]
    for spec in stage.get("expect_glob", []):
        exclude = set(spec.get("exclude", []))
        sources += [p for p in ROOT.glob(spec["pattern"])
                    if p.is_file() and rel(p) not in exclude]
    for f in sources:
        if not f.exists():
            continue
        target = dest / rel(f)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        kept.append(rel(f))
    return kept

def model_for(role):
    _, llm = resolve_profile(role)
    return llm or "?"

# ------------------------------------------------------------------ stages ----

def run_stage(stage, confirm, budget, max_iterations):
    role = stage["role"]
    workdir = workdir_for(role)
    label = stage["title"]
    brief1(f"{label}  [{stage['fr']}]  role={role}  workdir={workdir}")

    before = snapshot(stage["expect"])
    started, finished = {}, {}
    result = {
        "role": role,
        "title": label,
        "fr": stage["fr"],
        "workdir": workdir,
        "alias": model_for(role),
        "routed_to": route_of(role),
        "confirmation": confirm,
        "conversations": {},
        "expect": stage["expect"],
        "passed": False,
        "evidence": [],
    }
    t0 = time.time()

    if stage.get("parallel"):
        workers = stage["parallel"]
        for w in workers:
            letter, model, hostport = route_of(w)
            ok(f"{w} -> alias {model_for(w)} = {model} on endpoint {letter} ({hostport})")
        # Each worker resets, writes and integrates only the module it owns.
        # Scoping all three matters: a worker whose branch still holds the other
        # module's stub would otherwise overwrite the finished file with it.
        owned = {w: [f"workspace/demo-project/src/todoapp/{WORKER_MODULE[w]}"]
                 for w in workers}
        fan = run_workers(workers, confirm, max_iterations, budget, reset=owned)
        result["conversations"] = fan.get("conversations", {})
        result["marks"] = fan.get("marks", {})
        result["workdirs"] = fan.get("workdirs", {})
        # Integrate only after both finish, so a half-done worker cannot
        # half-apply into the tree the tester reads.
        merges = {}
        for w in workers:
            files, sha = commit_and_merge(w)
            # No commit means the branch still holds the stub. Taking it would
            # overwrite the main checkout's copy (and its staged version) with
            # the stub, so the stage fails on what is there instead.
            if not sha:
                bad(f"{w}: nothing committed on agent/{w}, not integrating")
            taken = integrate(w, owned[w]) if sha else []
            merges[w] = {"files": files, "sha": sha, "integrated": taken,
                         "ok": bool(taken),
                         "worktree_removed": drop_worktree(w, merge=False)}
        result["merges"] = merges
    else:
        # Same reason as the coders' reset: create cannot overwrite, so a file
        # left by an earlier run would make this run's write fail.
        for relpath in stage.get("reset", []):
            stale = ROOT / relpath
            if stale.exists():
                stale.unlink()
                ok(f"removed {relpath} from the last run so create can write it")
        before = snapshot(stage["expect"])
        extra = {}
        if stage.get("precommand"):
            extra["COMMAND_OUTPUT"] = run_precommand(stage, result)
        cid = run_role(role, confirm, workdir, started, finished,
                       max_iterations,
                       time.time() + budget if budget else None,
                       extra=extra)
        result["conversations"] = {role: cid}
        result["nudges"] = []
        deadline = time.time() + budget if budget else None
        for _ in range(NUDGES):
            missing = missing_files(stage, before)
            if not cid or not missing:
                break
            warn(f"{role} ended without writing {', '.join(missing)}; "
                 "asking it to write them")
            result["nudges"].append(missing)
            cid = nudge(cid, nudge_text(missing), finished, deadline) or cid
        result["duration_s"] = round((finished.get("t1", time.time())
                                      - started.get("t0", time.time())), 1)

    if stage.get("parallel"):
        result["duration_s"] = round(time.time() - t0, 1)

    missing = [w for w, cid in result["conversations"].items() if not cid]
    if missing:
        bad(f"no conversation for {', '.join(missing)}")
        result["passed"] = False
        return result

    passed, evidence = verify(stage, before)
    result["passed"] = passed
    result["evidence"] = evidence
    (ok if passed else bad)(f"{label}: "
                            + ("artifacts verified" if passed
                               else "artifacts missing or unconvincing"))
    return result

# Follow-up turns per stage when a role ends with files unwritten. Two is
# enough in practice: a model that ignores a second, explicit "call
# file_editor create on this path" will not write it on the third.
NUDGES = 2

def run_precommand(stage, result):
    cmd = stage["precommand"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    text = re.sub(r"\x1b\[[0-9;]*m", "", proc.stdout + proc.stderr)
    result["precommand"] = {"command": " ".join(cmd), "exit": proc.returncode}
    (ok if proc.returncode == 0 else warn)(
        f"{' '.join(cmd)} exited {proc.returncode}; its output goes to the agent")
    # The tail holds the per-check lines and the verdict; tracebacks above it
    # would push a small model past its useful context.
    return "\n".join(text.strip().splitlines()[-60:])

def missing_files(stage, before):
    """Expected files that are absent, empty, or untouched by this stage."""
    out = []
    for relpath in stage["expect"]:
        f = ROOT / relpath
        size = f.stat().st_size if f.exists() else 0
        if size < stage.get("min_bytes", 200) or size == before.get(relpath):
            out.append(relpath)
    return out

def nudge_text(missing):
    paths = "\n".join(f"- {WORKDIR}/{p}" for p in missing)
    return ("Your reply is not a deliverable: text in a message does not create "
            "a file, and these files still do not exist:\n\n"
            f"{paths}\n\n"
            "Call the `file_editor` tool now with `command` set to `create`, "
            "`path` set to the absolute path, and the whole file as `file_text`. One file per call. Do not "
            "answer in text until every file above exists.")

def commit_and_merge(worker):
    files, sha = commit_worktree(worker)
    return files, sha

# -------------------------------------------------------------------- main ----

def preflight():
    print(f"{BOLD}preflight{RESET}")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        bad("docker is not running - start Docker Desktop")
        return False
    ok("docker is running")
    if not start_stack():
        return False
    return show_state()

def run_pipeline(stages, confirm, budget, max_iterations, run_dir):
    results = []
    for stage in stages:
        result = run_stage(stage, confirm, budget, max_iterations)
        result["artifacts"] = copy_artifacts(stage, run_dir / "artifacts")
        results.append(result)
        if not result["passed"]:
            bad(f"stopping: {stage['title']} did not produce its artifacts. "
                "Later stages read what this one was supposed to write, so "
                "continuing would only produce confident-looking fiction.")
            warn(f"re-run just this stage with --stages {stage['role']}")
            break
        print()
    return results

def record(run_dir, results, meta):
    data = {"meta": meta, "stages": results}
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps(data, indent=2) + "\n")
    ok(f"evidence written to {rel(run_dir)}/run.json")

def compare(a, b):
    def load(d):
        p = Path(d)
        if p.is_dir() and (p / "run.json").exists():
            return p, json.loads((p / "run.json").read_text())
        # Also accept a bare timestamp under artifacts/runs.
        p = RUNS / d
        if (p / "run.json").exists():
            return p, json.loads((p / "run.json").read_text())
        return None, None

    pa, ra = load(a)
    pb, rb = load(b)
    if not ra or not rb:
        bad(f"could not read a run.json from {a!r} and {b!r}")
        return 1

    print(f"{BOLD}comparing{RESET}")
    print(f"  A  {rel(pa)}   started {ra['meta']['started']}")
    print(f"  B  {rel(pb)}   started {rb['meta']['started']}")
    print(f"\n  {'stage':<34}{'A':>10}{'B':>10}   verdict")
    print(f"  {'-'*34}{'-'*10}{'-'*10}   -------")

    same_shape = True
    names_a = [s["role"] for s in ra["stages"]]
    names_b = [s["role"] for s in rb["stages"]]
    if names_a != names_b:
        same_shape = False
        print(f"  stage order differs:\n    A: {names_a}\n    B: {names_b}")

    for sa, sb in zip(ra["stages"], rb["stages"]):
        mark_a = "verified" if sa["passed"] else "FAILED"
        mark_b = "verified" if sb["passed"] else "FAILED"
        verdict = "match" if sa["passed"] == sb["passed"] else "DIFFERS"
        if verdict == "DIFFERS":
            same_shape = False
        print(f"  {sa['role']:<34}{mark_a:>10}{mark_b:>10}   {verdict}")

    print("\n  artifacts per stage")
    all_art = sorted({p for s in ra["stages"] + rb["stages"]
                      for p in s.get("artifacts", [])})
    for p in all_art:
        in_a = any(p in s.get("artifacts", []) for s in ra["stages"])
        in_b = any(p in s.get("artifacts", []) for s in rb["stages"])
        flag = "" if in_a == in_b else "   <-- only in " + ("A" if in_a else "B")
        print(f"    {'A' if in_a else '.'} {'B' if in_b else '.'}  {p}{flag}")

    total_a = sum(s.get("duration_s") or 0 for s in ra["stages"])
    total_b = sum(s.get("duration_s") or 0 for s in rb["stages"])
    print(f"\n  agent wall-clock: A {total_a:.0f}s, B {total_b:.0f}s")

    print()
    if same_shape:
        ok("comparable: same stages, same order, same artifact set, same verdicts")
        print("  The wording differs between runs, which is expected and allowed:")
        print("  the requirement is comparable structure and progress, not identical text.")
        return 0
    warn("the two runs are NOT comparable - see the DIFFERS rows above")
    return 1

def main():
    argv = sys.argv[1:]
    if any(a in ("-h", "--help", "help") for a in argv):
        print((__doc__ or "").strip())
        return 0

    if len(argv) >= 3 and argv[0] == "--compare":
        return compare(argv[1], argv[2])

    confirm = DEFAULT_CONFIRMATION
    only, start_at = None, None
    budget, max_iterations = STAGE_BUDGET or None, MAX_ITERATIONS
    check_only = "--check" in argv

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--confirm" and i + 1 < len(argv):
            confirm, i = argv[i + 1], i + 2
        elif a == "--stages" and i + 1 < len(argv):
            only, i = [s.strip() for s in argv[i + 1].split(",") if s.strip()], i + 2
        elif a == "--from" and i + 1 < len(argv):
            start_at, i = argv[i + 1].strip(), i + 2
        elif a in ("--budget", "--max-iterations") and i + 1 < len(argv):
            try:
                value = int(argv[i + 1])
            except ValueError:
                bad(f"--{a.lstrip('-')} needs a whole number")
                return 1
            budget, max_iterations = ((value, max_iterations) if a == "--budget"
                                      else (budget, value))
            i += 2
        elif a in ("--check", "--run"):
            i += 1
        elif a.startswith("-"):
            bad(f"unknown flag {a}")
            return 1
        else:
            bad(f"unexpected argument {a!r}; stages are chosen with --stages "
                "or --from")
            return 1

    if confirm not in CONFIRMATION:
        bad(f"unknown confirmation mode {confirm!r}; "
            f"pick one of {', '.join(CONFIRMATION)}")
        return 1

    stages = STAGES
    if only:
        wanted = set(only)
        unknown = wanted - set(ROLES)
        if unknown:
            bad(f"unknown role(s): {', '.join(sorted(unknown))}; "
                f"pick from {', '.join(ROLES)}")
            return 1
        stages = [s for s in STAGES if s["role"] in wanted
                  or set(s.get("parallel", [])) & wanted]
        if not stages:
            bad(f"no stage runs {', '.join(sorted(wanted))}")
            return 1
    elif start_at:
        roles = [s["role"] for s in STAGES]
        if start_at not in roles:
            bad(f"unknown stage {start_at!r}; pick from {', '.join(roles)}")
            return 1
        stages = STAGES[roles.index(start_at):]

    print(f"{BOLD}pipeline{RESET}  "
          f"{len(stages)} stage(s): {', '.join(s['role'] for s in stages)}")
    print(f"confirmation={confirm}  per-stage budget="
          f"{budget if budget else 'none'}")

    if not preflight():
        return 1
    if check_only:
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS / stamp
    t0 = time.time()
    results = run_pipeline(stages, confirm, budget, max_iterations, run_dir)
    meta = {
        "started": stamp,
        "finished": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "wall_clock_s": round(time.time() - t0, 1),
        "confirmation": confirm,
        "stages_requested": [s["role"] for s in stages],
        "budget_s": budget,
        "roles": sorted(ROLES),
        # Record the routing so two runs can be compared on the same config.
        "routing": {name: {"url": url, "model": model, "roles": served}
                    for name, url, model, served in config_rows()},
    }
    record(run_dir, results, meta)

    brief1("summary")
    for r in results:
        secs = r.get("duration_s")
        timing = f"{secs:.0f}s" if secs else "-"
        print(f"  {r['fr']:<5} {r['role']:<16} {r['alias']:<16} "
              f"{timing:>7}  {'verified' if r['passed'] else 'FAILED'}")
    verified = sum(1 for r in results if r["passed"])
    print(f"\n  {verified}/{len(results)} stages verified their artifacts "
          f"in {meta['wall_clock_s']:.0f}s")

    left = [r["role"] for r in results if not r["passed"]]
    if left:
        bad(f"not delivered: {', '.join(left)}")
        return 1
    ok("all requested stages delivered their artifacts")
    return 0

if __name__ == "__main__":
    sys.exit(main())