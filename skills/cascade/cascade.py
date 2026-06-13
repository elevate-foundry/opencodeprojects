#!/usr/bin/env python3
"""cascade.py - speculative-decoding-style model cascade for pocket-agent.

Agent-layer analogue of speculative decoding: a cheap draft model (Haiku)
answers first and rates its own confidence; only low-confidence answers
escalate to the expensive verifier model (Sonnet). ~10x cheaper than
always using the big model, with quality preserved on hard queries.

Usage:
  cascade.py "<prompt>"
  cascade.py --force-big "<prompt>"     # skip draft, go straight to verifier
  cascade.py --threshold 8 "<prompt>"   # escalate if confidence < 8 (default 7)
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROXY = os.environ.get("FABLE_PROXY", "http://127.0.0.1:8377")
DRAFT_MODEL = os.environ.get("CASCADE_DRAFT_MODEL", "claude-haiku-4-5")
BIG_MODEL = os.environ.get("CASCADE_BIG_MODEL", "claude-sonnet-4-5")
THRESHOLD = int(os.environ.get("CASCADE_THRESHOLD", "7"))
MAX_TOKENS = int(os.environ.get("CASCADE_MAX_TOKENS", "1500"))
MAX_COST_USD = float(os.environ.get("CASCADE_MAX_COST_USD", "0.50"))
HIST = Path.home() / ".fable" / "cascade-history.jsonl"

PRICES = {  # per token (in, out)
    "claude-haiku-4-5": (1.00 / 1e6, 5.00 / 1e6),
    "claude-sonnet-4-5": (3.00 / 1e6, 15.00 / 1e6),
}

DRAFT_SYSTEM = (
    "Answer the user's question directly and well. Then on the very last "
    "line, alone, write CONFIDENCE: N where N is 0-10 — your honest rating "
    "of whether your answer is complete and correct. Rate low (<=6) if the "
    "question needs deep reasoning, niche expertise, long-form code, or "
    "you are unsure. Rate high (>=8) only when certain."
)

_cost = {"usd": 0.0}


def load_key():
    env = Path.home() / "opencodeprojects" / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("no ANTHROPIC_API_KEY in .env")


API_KEY = load_key()


def ask(model, prompt, system=None):
    if _cost["usd"] >= MAX_COST_USD:
        raise RuntimeError(f"cascade budget exhausted (${MAX_COST_USD})")
    payload = {"model": model, "max_tokens": MAX_TOKENS,
               "messages": [{"role": "user", "content": prompt}]}
    if system:
        payload["system"] = system
    req = urllib.request.Request(
        PROXY + "/v1/messages", data=json.dumps(payload).encode(),
        method="POST",
        headers={"content-type": "application/json", "x-api-key": API_KEY,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    u = out.get("usage", {})
    pin, pout = PRICES.get(model, PRICES[BIG_MODEL])
    _cost["usd"] += u.get("input_tokens", 0) * pin + u.get("output_tokens", 0) * pout
    return "".join(b.get("text", "") for b in out.get("content", []))


def cascade(prompt, threshold=THRESHOLD, force_big=False):
    path = "draft"
    confidence = None
    if force_big:
        answer = ask(BIG_MODEL, prompt)
        path = "forced-big"
    else:
        draft = ask(DRAFT_MODEL, prompt, system=DRAFT_SYSTEM)
        m = re.search(r"CONFIDENCE:\s*(\d+)\s*$", draft)
        confidence = int(m.group(1)) if m else 0
        answer = re.sub(r"\n?CONFIDENCE:\s*\d+\s*$", "", draft).strip()
        if confidence < threshold:
            path = "escalated"
            print(f"[cascade] draft confidence {confidence} < {threshold}; "
                  f"escalating to {BIG_MODEL}", file=sys.stderr)
            answer = ask(BIG_MODEL, prompt)
    with HIST.open("a") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prompt": prompt[:200], "path": path, "confidence": confidence,
            "cost_usd": round(_cost["usd"], 6),
        }) + "\n")
    print(f"[cascade] path={path} confidence={confidence} "
          f"cost=${_cost['usd']:.4f}", file=sys.stderr)
    return answer


def main():
    args = sys.argv[1:]
    force_big = "--force-big" in args
    if force_big:
        args.remove("--force-big")
    threshold = THRESHOLD
    if "--threshold" in args:
        i = args.index("--threshold")
        threshold = int(args[i + 1])
        del args[i:i + 2]
    if not args:
        sys.exit(__doc__.strip())
    print(cascade(" ".join(args), threshold=threshold, force_big=force_big))


if __name__ == "__main__":
    main()
