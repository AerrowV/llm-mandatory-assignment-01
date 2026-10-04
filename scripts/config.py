#!/usr/bin/env python3
"""Generate endpoints/config.yml and the 14 profile files from .env.

    python3 scripts/config.py            # write them
    python3 scripts/config.py --check    # fail if they have drifted from .env
"""

import json
import os
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
CONFIG_YML = ROOT / "endpoints" / "config.yml"
STATE = ROOT / "openhands" / "state"

# Role name == LiteLLM alias == profile name == prompt file, so one table
# resolves all four layers. coder-1/coder-2 differ only by name: each gets its
# own git worktree, which is the N>=2 fan-out for functional requirement 3.
ROLES = {
    "architect": "01-architect",
    "techlead": "02-tech-lead",
    "coder-1": "03-implementation",
    "coder-2": "03-implementation",
    "tester": "04-testing",
    "docs": "05-documentation",
    "deploy-validator": "06-deployment",
}

# The one file each worker owns, referenced as {{MODULE}}. Naming it is not
# cosmetic: left to infer which stub is its own, both workers narrated a plan
# instead of writing code.
WORKER_MODULE = {
    "coder-1": "storage.py",
    "coder-2": "server.py",
}

# Fixed id namespaces, so regenerating never orphans a bound profile.
_ID_NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

# Mirrors .env.example, so a missing .env gives working defaults.
DEFAULTS = {
    "LITELLM_MASTER_KEY": "sk-local-not-secure",
    "LITELLM_URL": "http://localhost:4000",
    "AGENT_URL": "http://localhost:8000",
    "LITELLM_BASE_URL": "http://litellm:4000",
    "WORKDIR": "/opt/project",
    "DEMO_PROJECT": "workspace/demo-project",
    "LITELLM_BIND": "127.0.0.1:4000",
    "AGENT_BIND": "127.0.0.1:8000",
    "ENDPOINT_A_HOST": "127.0.0.1",
    "ENDPOINT_A_PORT": "11434",
    "ENDPOINT_A_MODEL": "qwen2.5:3b",
    "ENDPOINT_A_ROLES": "architect,techlead,docs",
    "ENDPOINT_B_HOST": "127.0.0.1",
    "ENDPOINT_B_PORT": "11435",
    "ENDPOINT_B_MODEL": "qwen2.5:7b-instruct",
    "ENDPOINT_B_MODELS": "$HOME/.ollama-b/models",
    "ENDPOINT_B_ROLES": "coder-1,coder-2,tester,deploy-validator",
    # Containers cannot reach the host on 127.0.0.1; this is Docker's host alias.
    "CONTAINER_HOST": "host.docker.internal",
    "MAX_INPUT_TOKENS": "32768",
    "MAX_OUTPUT_TOKENS": "4096",
    "TEMPERATURE": "0",
    "LLM_TIMEOUT": "300",
    "MAX_ITERATIONS": "100",
    "STAGE_BUDGET": "1200",
    "CONFIRMATION": "never",
    "AGENT_CLASS": "CodeActAgent",
    # Only set true for a model measured by endpoints/toolcheck.py. A model that
    # returns the call as prose cannot drive an agent, whatever this says.
    "NATIVE_TOOL_CALLING": "true",
    "DISABLED_SKILLS": "",
}

_INT_VARS = {"MAX_INPUT_TOKENS", "MAX_OUTPUT_TOKENS", "LLM_TIMEOUT",
             "MAX_ITERATIONS", "STAGE_BUDGET", "ENDPOINT_A_PORT", "ENDPOINT_B_PORT"}

class ConfigError(Exception):
    pass

# ------------------------------------------------------------------- .env ----

def parse_env(text):
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        value = os.path.expanduser(value)
        value = re.sub(r"\$\{?(\w+)\}?", lambda m: os.environ.get(m.group(1), m.group(0)), value)
        out[key] = value
    return out

def load_env():
    values = dict(DEFAULTS)
    if ENV_FILE.exists():
        values.update(parse_env(ENV_FILE.read_text()))
    else:
        print(f"  [warn] no {ENV_FILE.name} - using the built-in defaults. "
              f"Run: cp .env.example .env")
    for key, raw in os.environ.items():
        if key in DEFAULTS:
            values[key] = raw
    # Derived, never configured: these used to be hardcoded in DEFAULTS, so
    # changing ENDPOINT_x_HOST left --check and the summary showing the old
    # address while requests went to the new one.
    for letter in ("A", "B"):
        values[f"ENDPOINT_{letter}_URL"] = (
            f"http://{values[f'ENDPOINT_{letter}_HOST']}"
            f":{values[f'ENDPOINT_{letter}_PORT']}")
    return values

def _int(values, key):
    try:
        return int(str(values[key]).strip())
    except (KeyError, ValueError):
        raise ConfigError(f"{key}={values.get(key)!r} is not a whole number")

def _bool(values, key):
    raw = str(values.get(key, "")).strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off", ""):
        return False
    raise ConfigError(f"{key}={values[key]!r} is not true or false")

def _csv(values, key):
    return [item.strip() for item in str(values.get(key, "")).split(",") if item.strip()]

# ------------------------------------------------------------------ roles ----

def endpoint_of(role, values):
    on_a, on_b = role in _csv(values, "ENDPOINT_A_ROLES"), role in _csv(values, "ENDPOINT_B_ROLES")
    if on_a and on_b:
        raise ConfigError(f"role {role!r} is listed on both endpoints in .env")
    return "A" if on_a else "B" if on_b else None

def route_of(role, values=None):
    """Where a role actually goes: (endpoint letter, physical model, host:port).

    The alias alone is not evidence. A LiteLLM fallback serves the turn from the
    other endpoint and the alias never changes, so run evidence that records only
    the alias cannot tell a real run from a fallback run.
    """
    values = load_env() if values is None else values
    letter = endpoint_of(role, values)
    if letter is None:
        return None, None, None
    model = values[f"ENDPOINT_{letter}_MODEL"]
    host = values[f"ENDPOINT_{letter}_HOST"]
    port = values[f"ENDPOINT_{letter}_PORT"]
    return letter, model, f"{host}:{port}"

def check_roles(values):
    unrouted = [r for r in ROLES if not endpoint_of(r, values)]
    if unrouted:
        raise ConfigError(
            "no endpoint in .env serves: " + ", ".join(sorted(unrouted))
            + "\n  Add each one to ENDPOINT_A_ROLES or ENDPOINT_B_ROLES.")
    known = set(ROLES)
    stray = [r for name in ("ENDPOINT_A_ROLES", "ENDPOINT_B_ROLES")
             for r in _csv(values, name) if r not in known]
    if stray:
        raise ConfigError(".env routes roles that do not exist: " + ", ".join(sorted(set(stray)))
                          + "\n  Valid roles: " + ", ".join(sorted(known)))

# ------------------------------------------------------------ config.yml ----

CONFIG_HEADER = """\
# GENERATED FILE - do not edit. Source of truth is .env; regenerate with
#     python3 scripts/config.py
#
# One alias per role. Code references the alias, never a server, so moving a
# role is a .env edit plus `docker compose restart litellm`.
#
# Three settings here are measured, not chosen (evidence in SYNOPSIS.md):
#   1. openai/<model> on ollama's /v1 route, never ollama_chat/ - the latter
#      re-serialises parallel tool calls under index=0 and concatenates their
#      argument JSON, which OpenHands rejects as unparseable.
#   2. max_input_tokens is not lowered: one agent request is ~20k tokens and
#      LiteLLM silently truncates against this value.
#   3. No master_key and no DATABASE_URL: either moves auth onto LiteLLM's
#      virtual-key path, which 400s every turn with "No connected db" while
#      /v1/models still answers. The key arrives as LITELLM_MASTER_KEY via
#      docker-compose env_file, and store_model_in_db stays false for the same
#      reason.
"""

def render_config_yml(values):
    host = values["CONTAINER_HOST"]
    fallback = next(r for r in ROLES if endpoint_of(r, values) == "A")
    out = [CONFIG_HEADER, "\nmodel_list:\n"]
    for letter in ("A", "B"):
        model = values[f"ENDPOINT_{letter}_MODEL"]
        api_base = f"http://{host}:{values[f'ENDPOINT_{letter}_PORT']}/v1"
        served = [r for r in ROLES if endpoint_of(r, values) == letter]
        out.append(f"  # Endpoint {letter}: {len(served)} role(s) - {', '.join(served)}.\n")
        out.append(f"  # {model} on {host}:{values[f'ENDPOINT_{letter}_PORT']}"
                   " (ollama's OpenAI-compatible /v1 route)\n")
        for role in served:
            out.append(f"""
  - model_name: {role}
    litellm_params:
      model: openai/{model}
      api_base: {api_base}
      api_key: ollama
      # Sent on every call. OpenHands sends no max_tokens and model_info is
      # metadata only, so without this ollama generates until the context is
      # full: a looping model held one tester turn open for 16+ minutes.
      max_tokens: {_int(values, 'MAX_OUTPUT_TOKENS')}
    model_info:
      id: {model}
      mode: chat
      supports_function_calling: {_bool(values, 'NATIVE_TOOL_CALLING')}
      max_input_tokens: {_int(values, 'MAX_INPUT_TOKENS')}
      max_output_tokens: {_int(values, 'MAX_OUTPUT_TOKENS')}
""")
    out.append(f"""
litellm_settings:
  drop_params: true
  request_timeout: {_int(values, 'LLM_TIMEOUT')}
  num_retries: 2
  # Fallback beats a dead run, but then the alias no longer names the model that
  # served, so a run record has to log the model actually used.
  fallbacks:
""")
    for role in ROLES:
        if endpoint_of(role, values) == "B":
            out.append(f"    - {role}: [{fallback}]\n")
    out.append("""
router_settings:
  routing_strategy: simple-shuffle
  num_retries: 2

general_settings:
  store_model_in_db: false
""")
    return "".join(out)

# --------------------------------------------------------------- profiles ----

def _stable_id(kind, role, path):
    if path.exists():
        try:
            existing = json.loads(path.read_text()).get("id")
            if existing:
                return existing
        except (json.JSONDecodeError, OSError):
            pass
    return str(uuid.uuid5(_ID_NS, f"{ROOT.name}/{kind}/{role}"))

def render_profiles(values):
    out, temperature, timeout = {}, _int_float(values, "TEMPERATURE"), _int(values, "LLM_TIMEOUT")
    native = _bool(values, "NATIVE_TOOL_CALLING")
    skills = _csv(values, "DISABLED_SKILLS")
    for role in ROLES:
        letter = endpoint_of(role, values)

        llm_path = STATE / "profiles" / f"{role}.json"
        out[llm_path] = {
            "base_url": values["LITELLM_BASE_URL"],
            "auth_type": "api_key",
            # Literal key, never "os.environ/LITELLM_MASTER_KEY": OpenHands does
            # not expand it, and LiteLLM reads the unresolved string as an unknown
            # key and 400s every turn while /v1/models still answers. Committing
            # it is safe only because every port binds to 127.0.0.1.
            "api_key": values["LITELLM_MASTER_KEY"],
            "api_mode": "chat",
            "timeout": timeout,
            "model": f"openai/{role}",
            "native_tool_calling": native,
            "temperature": temperature,
            "_comment": f"generated by scripts/config.py - edit .env, not this file. "
                        f"alias '{role}' -> {values[f'ENDPOINT_{letter}_MODEL']} "
                        f"on endpoint {letter}",
        }

        agent_path = STATE / "agent-profiles" / f"{role}.json"
        out[agent_path] = {
            "schema_version": 2,
            "id": _stable_id("agent-profile", role, agent_path),
            "name": role,
            "agent_kind": "openhands",
            "llm_profile_ref": role,
            "agent": values["AGENT_CLASS"],
            "disabled_skills": skills,
        }
    return out

def _int_float(values, key):
    try:
        return float(str(values[key]).strip())
    except (KeyError, ValueError):
        raise ConfigError(f"{key}={values.get(key)!r} is not a number")

# ----------------------------------------------------------------- output ----

def _write(path, text, dry_run):
    if path.exists() and path.read_text() == text:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return True

def sync(dry_run=False, quiet=False):
    values = load_env()
    check_roles(values)
    messages = []

    if _write(CONFIG_YML, render_config_yml(values), dry_run):
        messages.append(f"{CONFIG_YML.relative_to(ROOT)}")

    for path, data in sorted(render_profiles(values).items()):
        text = json.dumps(data, indent=2) + "\n"
        if _write(path, text, dry_run):
            messages.append(str(path.relative_to(ROOT)))

    if messages and not quiet:
        verb = "would write" if dry_run else "wrote"
        print(f"  [{verb}] {len(messages)} file(s) from .env:")
        for name in messages:
            print(f"           {name}")
    return bool(messages), messages

def summary(values):
    rows = []
    for letter in ("A", "B"):
        served = [r for r in ROLES if endpoint_of(r, values) == letter]
        rows.append((f"endpoint {letter}",
                     f"{values[f'ENDPOINT_{letter}_URL']}  {values[f'ENDPOINT_{letter}_MODEL']}",
                     ", ".join(served)))
    return rows

def main():
    dry_run = "--check" in sys.argv[1:]
    try:
        changed, _ = sync(dry_run=dry_run)
    except ConfigError as exc:
        print(f"  [FAIL] {exc}")
        return 1
    values = load_env()
    print("\n  .env resolves to:")
    for name, where, roles in summary(values):
        print(f"    {name:<12} {where}")
        print(f"    {'':<12} roles: {roles}")
    print(f"\n  {'drift found' if changed else 'in sync with .env'}"
          + ("  (nothing written; drop --check to apply)" if changed and dry_run else ""))
    return 0

if __name__ == "__main__":
    sys.exit(main())