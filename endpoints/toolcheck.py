#!/usr/bin/env python3
"""Does a model emit a *structured* tool call, or prose that looks like one?

    python3 endpoints/toolcheck.py --endpoint B
    python3 endpoints/toolcheck.py --endpoint B --via-proxy --model tester
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# config.py is the only reader of .env, so this cannot disagree with the stack.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from config import load_env  # noqa: E402

ENV = load_env()
KEY = ENV["LITELLM_MASTER_KEY"]
PROXY = ENV["LITELLM_URL"]

TOOL = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Write text to a file on disk.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute file path."},
                "text": {"type": "string", "description": "Contents to write."},
            },
            "required": ["path", "text"],
        },
    },
}

PROMPT = "Write the file /tmp/check.txt containing the word OK. Use the tool."

def post(url, payload, headers=None, timeout=180):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode()[:400]}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}

def report(resp):
    if "_error" in resp or "_http_error" in resp:
        return "failed", json.dumps(resp)[:400]

    choices = resp.get("choices") or []
    if not choices:
        return "failed", "no choices in response"
    msg = choices[0].get("message", {})

    calls = msg.get("tool_calls")
    if calls:
        parts = []
        for c in calls:
            fn = c.get("function", {})
            parts.append(f"{fn.get('name')}({fn.get('arguments')})")
        return "native", f"{len(calls)} structured call(s): " + "; ".join(parts)

    text = (msg.get("content") or "").strip()
    if not text:
        return "failed", "empty content and no tool_calls"
    looks_like_call = any(k in text for k in ('"name"', "'name'", "write_file", "{"))
    kind = "text that looks like a call" if looks_like_call else "prose"
    return "text", f"{kind}, {len(text)} chars: {text[:200]!r}"

def first_alias(letter):
    """A role alias LiteLLM actually serves for this endpoint."""
    values = load_env()
    roles = [r.strip() for r in values[f"ENDPOINT_{letter}_ROLES"].split(",") if r.strip()]
    if not roles:
        raise SystemExit(f"no roles are routed to endpoint {letter} in .env")
    return roles[0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint", choices=("A", "B"), default="A",
                   help="which .env endpoint to check; sets --port and --model")
    p.add_argument("--port", type=int, help="override the endpoint's port")
    p.add_argument("--model", help="override the endpoint's model")
    p.add_argument("--via-proxy", action="store_true",
                   help="go through LiteLLM using a role alias as the model name")
    p.add_argument("--stream", action="store_true",
                   help="also test streaming; OpenHands always streams")
    args = p.parse_args()
    host = ENV[f"ENDPOINT_{args.endpoint}_HOST"]
    port = args.port or int(ENV[f"ENDPOINT_{args.endpoint}_PORT"])

    # LiteLLM only knows role aliases, never the physical model name, so an
    # un-overridden --via-proxy has to send an alias. Direct-to-endpoint calls
    # want the real model.
    if args.via_proxy:
        model = args.model or first_alias(args.endpoint)
        url, headers = f"{PROXY}/v1/chat/completions", {
            "Authorization": f"Bearer {KEY}"}
        label = f"proxy {PROXY} -> {model}"
    else:
        model = args.model or ENV[f"ENDPOINT_{args.endpoint}_MODEL"]
        url, headers = f"http://{host}:{port}/v1/chat/completions", {}
        label = f"endpoint {args.endpoint} {host}:{port} -> {model}"

    payload = {"model": model,
               "messages": [{"role": "user", "content": PROMPT}],
               "tools": [TOOL], "temperature": 0, "max_tokens": 512}

    print(f"\n=== {label} ===")
    verdict, detail = report(post(url, payload, headers))
    print(f"  non-streaming: {verdict}\n    {detail}")
    native = verdict == "native"

    if args.stream:
        payload["stream"] = True
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json",
                                              **headers})
        # Group fragments by tool-call index as a strict client does. One
        # buffer would hide the bug this catches: parallel calls all emitted
        # under index=0, merging two valid calls into one unparseable one.
        by_index, finish = {}, ""
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                for line in r:
                    line = line.decode().strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    for ch in obj.get("choices", []):
                        delta = ch.get("delta", {})
                        for tc in delta.get("tool_calls") or []:
                            idx = tc.get("index", 0)
                            slot = by_index.setdefault(idx, {"name": "", "args": ""})
                            fn = tc.get("function", {})
                            slot["name"] += fn.get("name") or ""
                            slot["args"] += fn.get("arguments") or ""
                        if delta.get("content"):
                            finish += delta["content"]
        except Exception as e:
            print(f"  streaming:     failed\n    {type(e).__name__}: {e}")
        else:
            if by_index:
                print(f"  streaming:     native, {len(by_index)} call(s) "
                      f"at index {sorted(by_index)}")
                for idx in sorted(by_index):
                    slot = by_index[idx]
                    try:
                        json.loads(slot["args"])
                        print(f"    index {idx}: {slot['name']}({slot['args']}) - valid JSON")
                    except json.JSONDecodeError as e:
                        print(f"    index {idx}: {slot['name']}({slot['args']})"
                              f" - INVALID JSON: {e}")
                        native = False
                if not native:
                    print("    ^ merged or malformed; OpenHands will reject this turn")
            elif finish.strip():
                print(f"  streaming:     text\n    {finish[:200]!r}")
            else:
                print("  streaming:     failed\n    no tool calls and no content")

    print(f"\n  VERDICT: {'PASS - can drive an agent' if native else 'FAIL - not tool-call capable'}")
    return 0 if native else 1

if __name__ == "__main__":
    sys.exit(main())
