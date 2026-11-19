"""`ask("backend:model", prompt)` across subscriptions (claude, codex, opencode) and APIs (openrouter, google, openai).

Subscription CLIs run headless in an empty temp dir with no tools, project config or memory, so the
model only sees `system` + `prompt`. They accept `effort` but no sampling params: use an API backend
when temperature/seed must be controlled. `thinking=False` (claude) or `effort="none"` (codex) turns hidden
reasoning off, and the call fails unless the provider reports exactly 0 reasoning tokens. Every Reply records
`thinking_tokens` as reported (None when the provider gave no count), so a run can prove its off arm had none.
"""

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field

DEFAULT_SYSTEM = "You are a helpful assistant."
APIS = {
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "google": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
}
CLI_PARAMS = {"claude": {"effort", "thinking"}, "codex": {"effort"}, "opencode": set()}


@dataclass
class Reply:
    text: str
    resolved: str = ""  # model id the provider actually served
    usage: dict = field(default_factory=dict)
    seconds: float = 0.0
    thinking_tokens: int | None = None  # hidden reasoning the provider reported; None = not reported


def _cli(cmd, strip_env=(), extra_env=None):
    # strip_env: name prefixes to drop, so an API key, base URL or a parent session's thinking setting
    # can't leak into the child (subscription auth comes from the CLI's own login)
    env = {k: v for k, v in os.environ.items() if not k.startswith(strip_env)} | (extra_env or {})
    with tempfile.TemporaryDirectory() as cwd:
        p = subprocess.run(
            cmd,
            check=False,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=300,
        )
    if p.returncode:
        # codex prints its API error as JSON on stdout and only a banner on stderr, so keep both tails
        raise RuntimeError(
            f"{cmd[0]} exit {p.returncode}: {p.stderr.strip()[-200:]} | {p.stdout.strip()[-400:]}"
        )
    return p.stdout


def _claude(model, prompt, system, effort=None, thinking=True):
    cmd = ["claude", "-p", prompt, "--model", model, "--system-prompt", system or DEFAULT_SYSTEM,
           "--tools", "", "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
           "--disable-slash-commands", "--output-format", "json"]  # fmt: skip
    if effort:
        cmd += ["--effort", effort]
    # The CLI sends thinking "disabled" only for models it knows accept it (e.g. claude-haiku-4-5,
    # claude-sonnet-5); for newer ones (haiku 5.5) it silently keeps adaptive thinking, hence the check.
    env = None if thinking else {"MAX_THINKING_TOKENS": "0"}
    strip = ("ANTHROPIC_", "CLAUDE_CODE_", "CLAUDECODE", "MAX_THINKING_TOKENS")
    r = json.loads(_cli(cmd, strip_env=strip, extra_env=env))
    if r.get("is_error"):
        raise RuntimeError(r.get("result"))
    usage = r.get("usage", {})
    think = usage.get("output_tokens_details", {}).get("thinking_tokens")
    if not thinking and think != 0:
        raise RuntimeError(
            f"{model} reported {think} thinking tokens with thinking off; can't verify the off arm"
        )
    return Reply(r["result"], ",".join(r.get("modelUsage", {})) or model, usage, thinking_tokens=think)


def _codex(model, prompt, system, effort=None):
    cmd = ["codex", "exec", prompt, "-m", model, "--skip-git-repo-check", "--ephemeral",
           "--ignore-user-config", "--ignore-rules", "-s", "read-only", "--json",
           "-c", f"developer_instructions={json.dumps(system or DEFAULT_SYSTEM)}"]  # fmt: skip
    if effort:
        cmd += ["-c", f"model_reasoning_effort={effort}"]
    events = [json.loads(line) for line in _cli(cmd, strip_env=("OPENAI_", "CODEX_")).splitlines()]
    done = next((e for e in events if e.get("type") == "turn.completed"), None)
    text = [e["item"]["text"] for e in events if e.get("item", {}).get("type") == "agent_message"]
    if done is None or not text or not text[-1].strip():
        raise RuntimeError(
            f"codex: no completed turn with a final message ({[e.get('type') for e in events]})"
        )
    usage = done.get("usage", {})
    think = usage.get("reasoning_output_tokens")
    if effort == "none" and think != 0:
        raise RuntimeError(
            f"{model} reported {think} reasoning tokens at effort none; can't verify the off arm"
        )
    return Reply(text[-1], model, usage, thinking_tokens=think)


def _opencode(model, prompt, system):
    full = f"{system}\n\n{prompt}" if system else prompt  # opencode run has no system-prompt flag
    events = [
        json.loads(line)
        for line in _cli(["opencode", "run", "-m", model, "--format", "json", full]).splitlines()
    ]
    parts = [e["part"] for e in events if "part" in e]
    usage = next((p["tokens"] for p in reversed(parts) if p.get("type") == "step-finish"), {})
    text = "".join(p["text"] for p in parts if p.get("type") == "text")
    return Reply(text, model, usage, thinking_tokens=usage.get("reasoning"))


def _api(backend, model, prompt, system, thinking=None, **params):
    """`thinking` (openrouter only) sends OpenRouter's unified `reasoning: {enabled: ...}`; with
    thinking=False the call fails unless the reply reports exactly 0 reasoning tokens and no reasoning text."""
    from openai import OpenAI

    if thinking is not None:
        if backend != "openrouter":
            raise ValueError(f"thinking= is wired for openrouter only; pass {backend}'s own reasoning params")
        params["extra_body"] = params.get("extra_body", {}) | {"reasoning": {"enabled": thinking}}
    base_url, key_env = APIS[backend]
    client = OpenAI(base_url=base_url, api_key=os.environ.get(key_env), max_retries=5)
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    r = client.chat.completions.create(model=model, messages=messages, **params)
    usage = r.usage.model_dump() if r.usage else {}
    think = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    msg = r.choices[0].message
    extra = msg.model_extra or {}  # routes name the reasoning channel differently
    shown = extra.get("reasoning") or extra.get("reasoning_content") or extra.get("reasoning_details")
    if thinking is False and (think != 0 or shown):
        raise RuntimeError(
            f"{model} reported {think} reasoning tokens (text: {bool(shown)}) with thinking off"
        )
    provider = (r.model_extra or {}).get("provider")  # openrouter may route one id to different hosts
    return Reply(
        msg.content or "", f"{r.model}@{provider}" if provider else r.model, usage, thinking_tokens=think
    )


def ask(spec: str, prompt: str, system: str | None = None, **params) -> Reply:
    """spec = 'backend:model', e.g. 'claude:opus', 'codex:gpt-6-sol', 'openrouter:qwen/qwen3.5-72b'."""
    backend, model = spec.split(":", 1)
    t = time.monotonic()
    if backend in APIS:
        reply = _api(backend, model, prompt, system, **params)
    elif backend in CLI_PARAMS:
        unsupported = set(params) - CLI_PARAMS[backend]
        if unsupported:
            raise ValueError(f"{backend} CLI can't set {sorted(unsupported)}; use an API backend")
        reply = {"claude": _claude, "codex": _codex, "opencode": _opencode}[backend](
            model, prompt, system, **params
        )
    else:
        raise ValueError(f"unknown backend '{backend}' (claude, codex, opencode, {', '.join(APIS)})")
    reply.seconds = round(time.monotonic() - t, 2)
    return reply
