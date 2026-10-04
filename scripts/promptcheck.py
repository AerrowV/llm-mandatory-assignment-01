#!/usr/bin/env python3
"""Static checks on the role prompts, plus optional live replays.

    python3 scripts/promptcheck.py           # static only, no services needed
    python3 scripts/promptcheck.py --live    # also replay each prompt on its endpoint
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from config import (  # noqa: E402  sibling module, and the only thing that reads .env
    CONFIG_YML,
    ROLES,
    endpoint_of,
    load_env,
)

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"

# Per-endpoint char ceilings, measured against the real agent request: the 7b
# handled 3506 chars on B but failed at 3207 once combined with the full system
# prompt and all 20 schemas, where it emitted an empty message. A's 3b took 5074.
LENGTH_BUDGET = {"A": 6000, "B": 3500}

# Headings the pipeline verifies. Edit one away and the role still runs and still
# writes files, it just quietly stops producing what is checked for.
REQUIRED_HEADINGS = {
    "01-architect": ["## Core Objective", "## Deliverables"],
    "02-tech-lead": ["## Deliverables", "## How to write the files",
                     "## Output Format"],
    "03-implementation": ["## Core Objective", "## The task"],
    "04-testing": ["## Core Objective", "## The task", "## Output Format"],
    "05-documentation": ["## Core Objective", "## The task", "## Output Format"],
    "06-deployment": ["## Core Objective", "## The task", "## Output Format"],
}

# Small but enough to make the model reach for a tool rather than answer in prose.
TOOLS = [
    {"type": "function", "function": {
        "name": "file_editor", "description": "Create, view or edit a file.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "enum": ["create", "view", "str_replace"]},
            "path": {"type": "string", "description": "Absolute path."},
            "file_text": {"type": "string"}}, "required": ["command", "path"]}}},
    {"type": "function", "function": {
        "name": "terminal", "description": "Run a shell command.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
]

PASS, FAIL = "  [ok]   ", "  [FAIL] "

def render(text, role, env):
    from agent import DEMO, WORKDIR, WORKER_MODULE
    workdir = f"{WORKDIR}/{DEMO}" if role in ("coder-1", "coder-2", "tester", "docs") else WORKDIR
    for placeholder, value in (("{{WORKDIR}}", workdir),
                               ("{{MODULE}}", WORKER_MODULE.get(role, "")),
                               ("{{ROLE}}", role), ("{{ROOT}}", WORKDIR),
                               # filled at run time by the stage's precommand
                               ("{{COMMAND_OUTPUT}}", "(validate.sh output)")):
        text = text.replace(placeholder, value)
    return text

def static_checks(env, quiet=False):
    bad = 0
    for role, stem in ROLES.items():
        letter = endpoint_of(role, env)
        path = PROMPTS / f"{stem}.md"
        budget = LENGTH_BUDGET[letter]

        if not path.exists():
            print(f"{FAIL}{role:<17} no prompt at prompts/{stem}.md")
            bad += 1
            continue

        raw = path.read_text()
        text = render(raw, role, env)
        problems = []

        leftover = [w for w in text.split() if w.startswith("{{") and w.endswith("}}")]
        if leftover:
            problems.append(f"unreplaced placeholder {sorted(set(leftover))}")
        missing = [h for h in REQUIRED_HEADINGS.get(stem, []) if h not in raw]
        if missing:
            problems.append(f"missing heading(s) {missing}")
        if len(raw) > budget:
            problems.append(f"{len(raw)} chars, over the {budget} verified for endpoint {letter}")

        if problems:
            print(f"{FAIL}{role:<17} prompts/{path.name}: " + "; ".join(problems))
            bad += 1
        elif not quiet:
            print(f"{PASS}{role:<17} {len(raw):>5} chars  endpoint {letter}  "
                  f"({len(raw) * 100 // budget}% of budget)")

    n = len(ROLES) - bad
    print(f"\n  {n}/{len(ROLES)} prompts pass the static checks")
    return bad

def live_check(role, stem, env, timeout):
    letter = endpoint_of(role, env)
    text = render((PROMPTS / f"{stem}.md").read_text(), role, env)
    payload = {"model": env[f"ENDPOINT_{letter}_MODEL"],
               "messages": [{"role": "user", "content": text}],
               "tools": TOOLS, "temperature": 0, "max_tokens": 512}
    req = urllib.request.Request(
        f"{env[f'ENDPOINT_{letter}_URL']}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"  [warn] {role}: endpoint {letter} did not answer ({exc})")
        return None

    message = (body.get("choices") or [{}])[0].get("message") or {}
    calls = message.get("tool_calls")
    if calls:
        print(f"{PASS}{role:<17} called {calls[0]['function']['name']} "
              f"(endpoint {letter}, {body.get('usage', {}).get('completion_tokens')} tokens)")
        return True
    # The silent failure: HTTP 200, no error, empty or prose content.
    text_out = (message.get("content") or "")[:120]
    print(f"{FAIL}{role:<17} no tool_calls from endpoint {letter}; content={text_out!r}")
    print(f"         {body.get('usage', {}).get('completion_tokens')} completion tokens "
          "emitted and discarded - the known empty-response failure")
    return False

def main():
    env = load_env()
    print("\n-- static --")
    bad = static_checks(env)
    if bad:
        return 1

    if "--live" not in sys.argv[1:]:
        return 0

    print("\n-- live (asks each role's model to act on its own prompt) --")
    print("  caveat: this sends a small representative tool set, not the real agent")
    print("  request. A pass here is a smoke test. endpoints/toolcheck.py has the")
    print("  same limit, and neither one proves the agent loop works - that needs a")
    print("  real run: python3 scripts/pipeline.py --stages coder-1 --budget 1500\n")
    timeout = int(env["LLM_TIMEOUT"])
    live_bad = 0
    for role, stem in ROLES.items():
        if live_check(role, stem, env, timeout) is False:
            live_bad += 1
    print(f"\n  {len(ROLES) - live_bad}/{len(ROLES)} prompts produced a tool call")
    print(f"  routing came from .env via {CONFIG_YML.relative_to(ROOT)}")
    return 1 if live_bad else 0

if __name__ == "__main__":
    sys.exit(main())