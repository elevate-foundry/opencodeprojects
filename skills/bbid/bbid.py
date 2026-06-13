#!/usr/bin/env python3
"""bbid.py - BBID-style device + behavioral identity hash for pocket-agent.

Computes a device fingerprint (stable hardware/build signals) and a behavioral
fingerprint (session telemetry from skill-runs + audit activity), encodes both
as 8-dot braille (BBES-style: each byte -> U+2800+byte), and binds them into
the session identity record at ~/.fable/bbid-sessions.jsonl.

Every signal used is printed. Explicit, auditable identity - no hidden inference.

Usage: bbid.py [--quiet]   print identity record (and append to log)
       bbid.py --device    device hash only (for scripting)
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
LOG = os.path.join(HOME, ".fable", "bbid-sessions.jsonl")
RUNS = os.path.join(HOME, ".fable", "skill-runs.jsonl")


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except Exception:
        return ""


def braille(hexdigest, n=16):
    return "".join(chr(0x2800 + b) for b in bytes.fromhex(hexdigest)[:n])


def device_signals():
    return {
        "model": sh("getprop ro.product.model"),
        "build": sh("getprop ro.build.fingerprint"),
        "cpu_cores": sh("nproc"),
        "storage_blocks": sh("df " + HOME + " | tail -1 | awk '{print $2}'"),
        "termux_prefix": os.environ.get("PREFIX", ""),
        "user": sh("id -un"),
    }


def behavior_signals():
    """Session telemetry: skill usage pattern + activity rhythm. Explicit, not covert."""
    sig = {"skills_used": [], "runs_today": 0, "hour_utc": datetime.now(timezone.utc).hour}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if os.path.exists(RUNS):
        skills = []
        for line in open(RUNS):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("ts", "").startswith(today):
                sig["runs_today"] += 1
                skills.append(r.get("skill", "?"))
        sig["skills_used"] = sorted(set(skills))
    return sig


def main():
    quiet = "--quiet" in sys.argv
    dev = device_signals()
    dev_hash = hashlib.sha256(json.dumps(dev, sort_keys=True).encode()).hexdigest()
    if "--device" in sys.argv:
        print(dev_hash)
        return

    beh = behavior_signals()
    beh_hash = hashlib.sha256(json.dumps(beh, sort_keys=True).encode()).hexdigest()
    sess_hash = hashlib.sha256((dev_hash + beh_hash).encode()).hexdigest()

    rec = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "device_hash": dev_hash,
        "device_braille": braille(dev_hash),
        "behavior_hash": beh_hash,
        "session_id": sess_hash[:16],
        "session_braille": braille(sess_hash),
        "signals": {"device": dev, "behavior": beh},
    }
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps({k: v for k, v in rec.items() if k != "signals"}) + "\n")

    if quiet:
        print(rec["session_id"])
    else:
        print(f"BBID session identity ({rec['ts']})")
        print(f"  device   {rec['device_braille']}  {dev_hash[:16]}…")
        print(f"  session  {rec['session_braille']}  {rec['session_id']}")
        print("  signals used (all of them - nothing hidden):")
        for k, v in dev.items():
            print(f"    device.{k} = {v[:60]}")
        for k, v in beh.items():
            print(f"    behavior.{k} = {v}")
        print(f"  log -> {LOG}")


if __name__ == "__main__":
    main()
