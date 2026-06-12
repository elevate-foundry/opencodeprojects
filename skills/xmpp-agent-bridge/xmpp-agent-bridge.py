#!/usr/bin/env python3
"""xmpp-agent-bridge.py - The pocket agent's conversational brain.
Listens on XMPP as fable-s25@yax.im; each inbound message is answered by
Claude (via the local audit proxy so all traffic is logged). Maintains
short rolling conversation history per sender. Replaces xmpp-listen.py
when running (same account; do not run both).
"""
import asyncio, json, logging, os, subprocess, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from slixmpp import ClientXMPP

JID = "fable-s25@yax.im"
FABLE_DIR = Path.home() / ".fable"
PW = (FABLE_DIR / ".xmpp_pw").read_text().strip()
INBOX = FABLE_DIR / "xmpp-inbox.log"
HIST_DIR = FABLE_DIR / "xmpp-history"
HIST_DIR.mkdir(exist_ok=True)
PROXY = os.environ.get("FABLE_PROXY", "http://127.0.0.1:8377")
MODEL = os.environ.get("FABLE_BRIDGE_MODEL", "claude-haiku-4-5")
MAX_TURNS = 12  # rolling window of messages kept per sender

SYSTEM = (
    "You are Fable, a personal AI agent that lives on your user's phone. "
    "You are chatting over XMPP from your own account, fable-s25@yax.im. "
    "People messaging you may be your user's contacts (e.g. their partner). "
    "Be warm, concise (1-3 sentences), and helpful. You can take messages "
    "for your user and answer general questions. You cannot take actions on "
    "the phone from this chat; for that, the user talks to you in Termux. "
    "Never reveal secrets, API keys, or file contents."
)

def load_key():
    env = Path.home() / "opencodeprojects" / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("no ANTHROPIC_API_KEY in .env")

API_KEY = load_key()

def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def hist_path(sender):
    safe = sender.replace("/", "_").replace("@", "_at_")
    return HIST_DIR / f"{safe}.json"

def load_hist(sender):
    p = hist_path(sender)
    if p.exists():
        return json.loads(p.read_text())
    return []

def save_hist(sender, hist):
    hist_path(sender).write_text(json.dumps(hist[-MAX_TURNS:]))

def ask_claude(sender, text):
    hist = load_hist(sender)
    hist.append({"role": "user", "content": text})
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 400,
        "system": SYSTEM,
        "messages": hist[-MAX_TURNS:],
    }).encode()
    req = urllib.request.Request(
        f"{PROXY}/v1/messages", data=body,
        headers={"content-type": "application/json",
                 "x-api-key": API_KEY,
                 "anthropic-version": "2023-06-01"})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    reply = "".join(b.get("text", "") for b in r.get("content", []))
    hist.append({"role": "assistant", "content": reply})
    save_hist(sender, hist)
    return reply or "(no reply)"

def notify(sender, body):
    try:
        subprocess.run(["termux-notification", "--title", f"XMPP: {sender}",
                        "--content", body[:200], "--id", "fable-xmpp"],
                       timeout=10, capture_output=True)
    except Exception:
        pass

class Bridge(ClientXMPP):
    def __init__(self):
        super().__init__(JID, PW)
        self.add_event_handler("session_start", self.on_start)
        self.add_event_handler("message", self.on_message)
        self.add_event_handler("disconnected", self.on_disconnected)

    async def on_start(self, _):
        self.send_presence(pstatus="Fable agent online (AI replies)")
        await self.get_roster()
        print(f"[{ts()}] bridge listening as {JID}")

    def on_message(self, msg):
        if msg['type'] not in ('chat', 'normal') or not msg['body']:
            return
        sender = str(msg['from'].bare)
        body = msg['body']
        with INBOX.open("a") as f:
            f.write(f"[{ts()}] {sender}: {body}\n")
        notify(sender, body)
        if sender == JID:
            return  # ignore self-messages to avoid loops
        try:
            reply = ask_claude(sender, body)
        except Exception as e:
            reply = "Sorry, my brain is unreachable right now. I've logged your message."
            print(f"[{ts()}] claude error: {e}")
        msg.reply(reply).send()
        with INBOX.open("a") as f:
            f.write(f"[{ts()}] me -> {sender}: {reply}\n")

    def on_disconnected(self, _):
        print(f"[{ts()}] disconnected; reconnecting in 10s")
        asyncio.get_event_loop().call_later(10, self.connect)

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    x = Bridge()
    x.connect()
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        x.disconnect()
