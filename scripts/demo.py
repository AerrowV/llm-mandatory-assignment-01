#!/usr/bin/env python3
"""Run the whole demo and show what the AI team produced.

    python3 scripts/demo.py           # run the team (~15-20 min), then show the results
    python3 scripts/demo.py --show    # only show the results of the last run
"""

import json
import subprocess
import sys

from pipeline import DEMO, ROOT, RUNS, STAGES

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"


def title(text):
    print(f"\n{BOLD}== {text}{RESET}")


def sh(cmd, cwd=ROOT):
    out = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    return out.returncode, (out.stdout + out.stderr).strip()


def show_files():
    title("What each role produced")
    for stage in STAGES:
        print(f"  {stage['fr']}  {stage['role']}")
        for p in stage["files"]:
            f = ROOT / p
            size = f"{len(f.read_text().splitlines())} lines" if f.exists() else "missing"
            print(f"        {p}  {DIM}({size}){RESET}")


def show_run(run_dir):
    data = json.loads((run_dir / "run.json").read_text())
    title(f"Last run: {run_dir.name}")
    for letter, r in data["routing"].items():
        print(f"  endpoint {letter}: {r['model']:<14} {r['roles']}")
    print()
    for s in data["stages"]:
        mark = "verified" if s["passed"] else "FAILED"
        print(f"  {s['fr']}  {s['role']:<20} {s['seconds']:>5}s  {mark}")

    chat = run_dir / "team-chat.md"
    if chat.exists():
        title("Team chat (what the roles said to each other)")
        for line in chat.read_text().splitlines()[2:]:
            if line.strip():
                print("  " + (line[:200] + "..." if len(line) > 200 else line))


def show_app():
    title("The calculator the coders built")
    for args in ("add 2 3", "divide 5 2", "divide 1 0", "power 2 3"):
        code, out = sh(f"python3 run.py {args}", ROOT / DEMO)
        print(f"  $ python3 run.py {args:<12} -> {out}   {DIM}(exit {code}){RESET}")

    title("Tests")
    code, out = sh("python3 -m unittest discover -s tests", ROOT / DEMO)
    print(f"  {out.splitlines()[-1]}")

    title("Deployment validation (docker/validate.sh)")
    code, out = sh("./docker/validate.sh")
    for line in out.splitlines():
        if line.strip().startswith(("PASS", "FAIL", "==")) or "passed" in line or "deployable" in line:
            print("  " + line.strip())


def main():
    if sys.argv[1:2] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    if "--show" not in sys.argv[1:]:
        title("Running the AI team (python3 scripts/pipeline.py)")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "pipeline.py")], cwd=ROOT)

    runs = sorted(p for p in RUNS.glob("*") if (p / "run.json").exists())
    if not runs:
        print("no run recorded yet - run without --show first")
        return 1
    show_run(runs[-1])
    show_files()
    show_app()
    title("Where to look next")
    print(f"  team chat and run record   artifacts/runs/{runs[-1].name}/")
    print("  each coder's changes       git diff main agent/coder-1   (or agent/coder-2)")
    print("  live agent conversations   http://localhost:8000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
