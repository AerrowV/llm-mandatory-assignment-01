#!/usr/bin/env python3
"""Can a model disable thinking, and is it honest about thinking tokens?

    python3 endpoints/thinkcheck.py --endpoint B
"""

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# One .env, one parser; see scripts/config.py.
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
            "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
            "required": ["path", "text"],
        },
    },
}

PROMPT = "Write the file /tmp/check.txt containing the word OK. Use the tool."

# Ollama takes a bool or an effort string; "false" disables thinking.
THINK_MODES = [True, "low", "high", False]

def post(url, payload, headers=None, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode()[:300]}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}

def one_run(url, headers, model, think):
    payload = {"model": model, "messages": [{"role": "user", "content": PROMPT}],
               "tools": [TOOL], "temperature": 0, "max_tokens": 2048, "think": think}
    t0 = time.perf_counter()
    resp = post(url, payload, headers)
    dt = time.perf_counter() - t0
    if "_error" in resp or "_http_error" in resp:
        return {"think": think, "ok": False, "detail": json.dumps(resp)[:200], "secs": dt}

    usage = resp.get("usage", {}) or {}
    msg = (resp.get("choices") or [{}])[0].get("message", {}) or {}
    calls = msg.get("tool_calls")
    return {
        "think": think,
        "ok": bool(calls),
        "kind": "native" if calls else ("text" if (msg.get("content") or "").strip() else "empty"),
        # thinking tokens are reported separately when tracked
        "completion": usage.get("completion_tokens"),
        "reasoning": usage.get("completion_tokens_details", {}).get("reasoning_tokens")
        if isinstance(usage.get("completion_tokens_details"), dict) else None,
        "secs": dt,
    }

def first_alias(letter):
    """A role alias LiteLLM actually serves for this endpoint."""
    roles = [r.strip() for r in ENV[f"ENDPOINT_{letter}_ROLES"].split(",") if r.strip()]
    if not roles:
        raise SystemExit(f"no roles are routed to endpoint {letter} in .env")
    return roles[0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint", choices=("A", "B"), default="B",
                   help="which .env endpoint to check; sets --port and --model")
    p.add_argument("--port", type=int, help="override the endpoint's port")
    p.add_argument("--model", help="override the endpoint's model")
    p.add_argument("--via-proxy", action="store_true")
    p.add_argument("--runs", type=int, default=2, help="repeats per mode, to spot variance")
    args = p.parse_args()

    port = args.port or int(ENV[f"ENDPOINT_{args.endpoint}_PORT"])
    if args.via_proxy:
        # LiteLLM serves role aliases, not physical model names.
        model = args.model or first_alias(args.endpoint)
        url = f"{PROXY}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {KEY}"}
        label = f"{PROXY} -> {model}"
    else:
        model = args.model or ENV[f"ENDPOINT_{args.endpoint}_MODEL"]
        host = ENV[f"ENDPOINT_{args.endpoint}_HOST"]
        url = f"http://{host}:{port}/v1/chat/completions"
        headers = {}
        label = f"{host}:{port} -> {model}"
    print(f"\nposting to {url}")

    print(f"\n=== {label} ({args.runs} run(s) per mode) ===")
    print(f"{'think':<8} {'tool call':<10} {'latency':<18} {'completion tok':<16} reasoning")

    results, errors = [], []
    for think in THINK_MODES:
        runs = [one_run(url, headers, model, think) for _ in range(args.runs)]
        lat = [r["secs"] for r in runs]
        native = sum(1 for r in runs if r["ok"])
        toks = [r.get("completion") for r in runs if r.get("completion")]
        reas = [r.get("reasoning") for r in runs if r.get("reasoning")]
        results.append((think, native, lat, toks, reas))
        for r in runs:
            if r.get("detail"):
                errors.append(r["detail"])
        print(f"{str(think):<8} {f'{native}/{len(runs)}':<10} "
              f"{('%.1fs (min %.1f)' % (statistics.mean(lat), min(lat))):<18} "
              f"{(str(toks) if toks else '-'):<16} {reas or '-'}")

    print()
    if errors and not any(n for _, n, *_ in results):
        # Every run failed before the model could answer. Printing "no tool
        # calls" here blames the model for a bad URL or a dead server.
        print(f"  every run failed to reach the server ({len(errors)} failure(s)).")
        print(f"  first error: {errors[0]}")
        return 2
    good = [t for t, n, *_ in results if n == args.runs]
    bad = [t for t, n, *_ in results if n == 0]
    fastest = min(((statistics.mean(l), t) for t, n, l, *_ in results if n == args.runs),
                  default=(None, None))
    print(f"  modes with native tool calls every run: {good or 'none'}")
    print(f"  modes that never produced a tool call:  {bad or 'none'}")
    if fastest[1] is not None:
        print(f"  fastest reliable mode: think={fastest[1]} at {fastest[0]:.1f}s")
    return 0 if good else 1

if __name__ == "__main__":
    sys.exit(main())
