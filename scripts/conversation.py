#!/usr/bin/env python3
"""Drive one OpenHands conversation directly, for when a stage hangs.

    python3 scripts/conversation.py --role coder-1
"""

import json
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from config import load_env  # noqa: E402  the only thing that reads .env

API_KEY = ROOT / "openhands" / "state" / "agent-canvas" / "api-key.txt"
AGENT = load_env()["AGENT_URL"]

def api(path):
    req = urllib.request.Request(AGENT + path,
                                 headers={"X-Session-API-Key": API_KEY.read_text().strip()})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as exc:
        return {"_error": exc.code, "_body": exc.read().decode()[:300]}

def events(cid):
    data = api(f"/api/conversations/{cid}/events/search"
               f"?limit=100&sort_order=TIMESTAMP_DESC")
    if isinstance(data, dict) and "_error" in data:
        return []
    return data if isinstance(data, list) else data.get("events", data.get("items", []))

def text_of(content):
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content
                        if isinstance(p, dict))
    return str(content)

def show(cid, width):
    evts = events(cid)
    print(f"conversation {cid}\n{len(evts)} events\n")
    for e in reversed(evts):
        kind = e.get("kind")
        if kind == "ActionEvent":
            call = e.get("tool_call") or {}
            args = call.get("arguments")
            print(f"  TOOL   {call.get('name')}")
            print(f"         {str(args)[:width]}")
        elif kind == "ObservationEvent":
            body = text_of(e.get("observation", {}).get("content"))
            print(f"    <-   {body[:width]}")
        elif kind == "MessageEvent":
            msg = e.get("llm_message") or {}
            body = text_of(msg.get("content"))
            if body.strip():
                print(f"  {str(msg.get('role'))[:6].upper():<6} {body[:width]}")

def newest(role="architect"):
    runs = sorted((ROOT / "artifacts" / "runs").glob("*/run.json"))
    if not runs:
        print("no runs recorded yet")
        return None
    for run in reversed(runs):
        data = json.loads(run.read_text())
        for stage in data["stages"]:
            if role in stage["conversations"]:
                return stage["conversations"][role]
    return None

def main():
    args = sys.argv[1:]
    if any(a in ("-h", "--help", "help") for a in args):
        print((__doc__ or "").strip())
        return 0

    width = 400
    if "--width" in args:
        i = args.index("--width")
        width = int(args[i + 1])
        del args[i:i + 2]
    role = "architect"
    if args and args[0] in ("--last", "--role"):
        role = args[1] if len(args) > 1 else role
        args = []
    cid = args[0] if args else newest(role)
    if not cid:
        print("no conversation found; run scripts/pipeline.py first")
        return 1
    show(cid, width)
    return 0

if __name__ == "__main__":
    sys.exit(main())