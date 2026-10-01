#!/usr/bin/env python3
"""Measure a model's thinking mode: does it cost latency, and does it break tool calls?

Ollama advertises `thinking` as a model capability. When enabled, the model emits
a reasoning block before its answer, which for a tool-calling workload can mean
(a) extra tokens on every turn, and (b) the tool call arriving after a long
thinking prefix, or not at all.

This measures both, for each value Ollama accepts in `think`, and prints a table.
It is a measurement tool, not a config generator: decide from the numbers.

    python3 endpoints/thinkcheck.py --port 11435 --model qwen3:8b
    python3 endpoints/thinkcheck.py --via-proxy --model coder-1
"""

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

KEY = "sk-local-not-secure"  # throwaway loopback key, matches endpoints/.env

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

# Ollama accepts a bool or a literal effort string; "false" disables thinking.
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
        # thinking tokens are reported separately when the provider tracks them
        "completion": usage.get("completion_tokens"),
        "reasoning": usage.get("completion_tokens_details", {}).get("reasoning_tokens")
        if isinstance(usage.get("completion_tokens_details"), dict) else None,
        "secs": dt,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=11435)
    p.add_argument("--model", required=True)
    p.add_argument("--via-proxy", action="store_true")
    p.add_argument("--runs", type=int, default=2, help="repeats per mode, to spot variance")
    args = p.parse_args()

    if args.via_proxy:
        url, model = "http://localhost:4000/v1/chat/completions", args.model
        headers = {"Authorization": f"Bearer {KEY}"}
        label = f"proxy:4000 -> {model}"
    else:
        url, model = f"http://localhost:{args.port}/v1/chat/completions", args.model
        headers = {}
        label = f":{args.port} -> {model}"

    print(f"\n=== {label} ({args.runs} run(s) per mode) ===")
    print(f"{'think':<8} {'tool call':<10} {'latency':<18} {'completion tok':<16} reasoning")

    results = []
    for think in THINK_MODES:
        runs = [one_run(url, headers, model, think) for _ in range(args.runs)]
        lat = [r["secs"] for r in runs]
        native = sum(1 for r in runs if r["ok"])
        toks = [r.get("completion") for r in runs if r.get("completion")]
        reas = [r.get("reasoning") for r in runs if r.get("reasoning")]
        results.append((think, native, lat, toks, reas))
        print(f"{str(think):<8} {f'{native}/{len(runs)}':<10} "
              f"{('%.1fs (min %.1f)' % (statistics.mean(lat), min(lat))):<18} "
              f"{(str(toks) if toks else '-'):<16} {reas or '-'}")

    print()
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
