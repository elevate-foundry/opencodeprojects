#!/usr/bin/env python3
"""xmpp-send.py - Send an XMPP message as fable-s25@yax.im.
Usage: xmpp-send.py <to_jid> "<message>"
Password read from ~/.fable/.xmpp_pw"""
import asyncio, sys, logging
from pathlib import Path
from slixmpp import ClientXMPP

JID = "fable-s25@yax.im"
PW = (Path.home() / ".fable" / ".xmpp_pw").read_text().strip()

class Send(ClientXMPP):
    def __init__(self, to, body):
        super().__init__(JID, PW)
        self.to, self.body = to, body
        self.ok = False
        self.add_event_handler("session_start", self.go)
        self.add_event_handler("failed_auth", lambda e: print("FAILED: auth"))

    async def go(self, _):
        self.send_presence()
        self.send_message(mto=self.to, mbody=self.body, mtype='chat')
        print(f"SENT to {self.to}")
        self.ok = True
        self.disconnect()

if __name__ == "__main__":
    to, body = sys.argv[1], sys.argv[2]
    logging.basicConfig(level=logging.ERROR)
    x = Send(to, body)

    async def main():
        x.connect()
        try:
            await asyncio.wait_for(x.disconnected, timeout=30)
        except asyncio.TimeoutError:
            x.disconnect()

    asyncio.get_event_loop().run_until_complete(main())
    sys.exit(0 if x.ok else 1)
