#!/usr/bin/env python3
"""swarm.py - multi-agent synthesis skill for pocket-agent.

Hybrid of sal (role agents + Synth fusion), possible-minds (parallel swarm),
and v2_agi.py (persistent memory). Fans one prompt out to N role-agents in
parallel, then a Synth agent fuses the drafts into one answer. All LLM
traffic goes through the local audit proxy.

Usage:
  swarm.py "<prompt>"                 # full swarm -> synthesized answer
  swarm.py --verbose "<prompt>"       # also print each agent's draft
  swarm.py --roles codex,critic "<prompt>"
"""
import concurrent.futures
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROXY = os.environ.get("FABLE_PROXY", "http://127.0.0.1:8377")
MODEL = os.environ.get("FABLE_SWARM_MODEL", "claude-haiku-4-5")
SYNTH_MODEL = os.environ.get("FABLE_SWARM_SYNTH_MODEL", MODEL)
HIST = Path.home() / ".fable" / "swarm-history.jsonl"

# --- Governor: hard budget caps (env-overridable) ---
MAX_AGENTS = int(os.environ.get("SWARM_MAX_AGENTS", "3"))
MAX_TOKENS_PER_AGENT = int(os.environ.get("SWARM_MAX_TOKENS_PER_AGENT", "1200"))
MAX_SYNTH_TOKENS = int(os.environ.get("SWARM_MAX_SYNTH_TOKENS", "2000"))
MAX_PROMPT_CHARS = int(os.environ.get("SWARM_MAX_PROMPT_CHARS", "8000"))
MAX_COST_USD = float(os.environ.get("SWARM_MAX_COST_USD", "0.25"))
DAILY_COST_USD = float(os.environ.get("SWARM_DAILY_COST_USD", "2.00"))
# claude-haiku-4-5 pricing per token
PRICE_IN = 1.00 / 1e6
PRICE_OUT = 5.00 / 1e6

_run_cost = {"usd": 0.0}


def _spent_today():
    if not HIST.exists():
        return 0.0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total = 0.0
    for line in HIST.read_text().splitlines():
        try:
            rec = json.loads(line)
            if rec.get("ts", "").startswith(today):
                total += rec.get("cost_usd", 0.0)
        except (json.JSONDecodeError, TypeError):
            continue
    return total

ROLES = {
    "codex": "You are Codex, a precise engineer. Answer with concrete, "
             "technically rigorous detail. Prefer facts, numbers, working code.",
    "critic": "You are Critic, an adversarial reviewer. Answer the question, "
              "but lead with what could go wrong: risks, edge cases, flawed "
              "assumptions, counterarguments.",
    "dreamer": "You are Dreamer, a lateral thinker. Answer with the "
               "non-obvious angle: analogies, reframings, creative "
               "alternatives others would miss.",
}

SYNTH = ("You are Synth. You receive one question and several drafts from "
         "specialist agents. Fuse them into a single best answer: keep what "
         "they agree on, surface real disagreements briefly, drop fluff. "
         "Answer directly; do not mention the agents or drafts.")


def load_key():
    env = Path.home() / "opencodeprojects" / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("no ANTHROPIC_API_KEY in .env")


API_KEY = load_key()


def ask(system, prompt, model=MODEL, max_tokens=MAX_TOKENS_PER_AGENT):
    if _run_cost["usd"] >= MAX_COST_USD:
        raise RuntimeError(f"run budget exhausted (${MAX_COST_USD})")
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        PROXY + "/v1/messages", data=body, method="POST",
        headers={"content-type": "application/json",
                 "x-api-key": API_KEY,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    usage = out.get("usage", {})
    _run_cost["usd"] += (usage.get("input_tokens", 0) * PRICE_IN
                         + usage.get("output_tokens", 0) * PRICE_OUT)
    return "".join(b.get("text", "") for b in out.get("content", []))


def swarm(prompt, roles=None, verbose=False):
    if len(prompt) > MAX_PROMPT_CHARS:
        raise RuntimeError(
            f"prompt too long ({len(prompt)} > {MAX_PROMPT_CHARS} chars)")
    spent = _spent_today()
    if spent >= DAILY_COST_USD:
        raise RuntimeError(
            f"daily swarm budget exhausted (${spent:.2f} >= ${DAILY_COST_USD})")
    roles = roles or list(ROLES)
    if len(roles) > MAX_AGENTS:
        roles = roles[:MAX_AGENTS]
        print(f"[governor] capped to {MAX_AGENTS} agents: {roles}",
              file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(roles)) as ex:
        futs = {r: ex.submit(ask, ROLES[r], prompt) for r in roles}
        drafts = {}
        for r, f in futs.items():
            try:
                drafts[r] = f.result()
            except Exception as e:
                drafts[r] = f"[{r} failed: {e}]"
    if verbose:
        for r, d in drafts.items():
            print(f"--- {r} ---\n{d}\n", file=sys.stderr)
    fusion_input = f"QUESTION:\n{prompt}\n\n" + "\n\n".join(
        f"DRAFT ({r}):\n{d}" for r, d in drafts.items())
    answer = ask(SYNTH, fusion_input, model=SYNTH_MODEL,
                 max_tokens=MAX_SYNTH_TOKENS)
    with HIST.open("a") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prompt": prompt, "roles": roles, "answer": answer,
            "cost_usd": round(_run_cost["usd"], 6),
        }) + "\n")
    print(f"[cost] ${_run_cost['usd']:.4f} this run, "
          f"${spent + _run_cost['usd']:.4f} today", file=sys.stderr)
    return answer


def main():
    args = sys.argv[1:]
    verbose = "--verbose" in args
    if verbose:
        args.remove("--verbose")
    roles = None
    if "--roles" in args:
        i = args.index("--roles")
        roles = [r.strip() for r in args[i + 1].split(",")]
        bad = [r for r in roles if r not in ROLES]
        if bad:
            sys.exit(f"unknown roles: {bad}; available: {list(ROLES)}")
        del args[i:i + 2]
    if not args:
        sys.exit(__doc__.strip())
    print(swarm(" ".join(args), roles=roles, verbose=verbose))


if __name__ == "__main__":
    main()
