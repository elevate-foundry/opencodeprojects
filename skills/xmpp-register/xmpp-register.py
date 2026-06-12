#!/usr/bin/env python3
"""xmpp-register.py - Register a new XMPP account via in-band registration (XEP-0077).
Usage: xmpp-register.py <server> <username> <password>"""
import asyncio, sys, logging
from slixmpp import ClientXMPP
from slixmpp.exceptions import IqError, IqTimeout

class Register(ClientXMPP):
    def __init__(self, jid, password):
        super().__init__(jid, password)
        self.register_plugin('xep_0077')
        self['xep_0077'].force_registration = True
        self.add_event_handler("register", self.do_register)
        self.add_event_handler("session_start", self.on_start)
        self.ok = False

    async def do_register(self, iq):
        resp = self.Iq()
        resp['type'] = 'set'
        resp['register']['username'] = self.boundjid.user
        resp['register']['password'] = self.password
        try:
            await resp.send()
            print(f"REGISTERED: {self.boundjid.bare}")
            self.ok = True
        except IqError as e:
            print(f"FAILED: {e.iq['error']['condition']} {e.iq['error']['text']}")
        except IqTimeout:
            print("FAILED: timeout")
        self.disconnect()

    async def on_start(self, _):
        self.disconnect()

if __name__ == "__main__":
    server, user, pw = sys.argv[1], sys.argv[2], sys.argv[3]
    logging.basicConfig(level=logging.ERROR)
    x = Register(f"{user}@{server}", pw)

    async def main():
        x.connect()
        try:
            await asyncio.wait_for(x.disconnected, timeout=30)
        except asyncio.TimeoutError:
            x.disconnect()

    asyncio.get_event_loop().run_until_complete(main())
    sys.exit(0 if x.ok else 1)
