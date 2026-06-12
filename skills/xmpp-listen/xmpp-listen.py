#!/usr/bin/env python3
"""xmpp-listen.py - Listener daemon for fable-s25@yax.im.
Logs inbound messages to ~/.fable/xmpp-inbox.log, posts an Android
notification, and sends an auto-acknowledgement.
Usage: xmpp-listen.py            (foreground)
       nohup xmpp-listen.py &    (background daemon)
"""
import asyncio, logging, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from slixmpp import ClientXMPP

JID = "fable-s25@yax.im"
FABLE_DIR = Path.home() / ".fable"
PW = (FABLE_DIR / ".xmpp_pw").read_text().strip()
INBOX = FABLE_DIR / "xmpp-inbox.log"
AUTOREPLY = ("Hi, this is Fable (AI assistant). I got your message and logged it "
             "for my user. They'll see it next time we talk.")

class Listener(ClientXMPP):
    def __init__(self):
        super().__init__(JID, PW)
        self.add_event_handler("session_start", self.on_start)
        self.add_event_handler("message", self.on_message)
        self.add_event_handler("disconnected", self.on_disconnected)

    async def on_start(self, _):
        self.send_presence(pstatus="Fable agent online")
        await self.get_roster()
        print(f"[{ts()}] listening as {JID}")

    def on_message(self, msg):
        if msg['type'] not in ('chat', 'normal') or not msg['body']:
            return
        sender = str(msg['from'].bare)
        body = msg['body']
        line = f"[{ts()}] {sender}: {body}\n"
        with INBOX.open("a") as f:
            f.write(line)
        print(line, end="")
        notify(sender, body)
        if sender != JID:
            msg.reply(AUTOREPLY).send()

    def on_disconnected(self, _):
        print(f"[{ts()}] disconnected; reconnecting in 10s")
        asyncio.get_event_loop().call_later(10, self.connect)

def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def notify(sender, body):
    try:
        subprocess.run(
            ["termux-notification", "--title", f"XMPP: {sender}",
             "--content", body[:200], "--id", "fable-xmpp"],
            timeout=10, capture_output=True)
    except Exception:
        pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    x = Listener()
    x.connect()
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        x.disconnect()
