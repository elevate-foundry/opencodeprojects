# Pocket Agent — an AI that lives in your phone

A phone-native autonomous agent built on [opencode](https://github.com/opencode-ai/opencode) + Termux + Anthropic.
It remembers you, has its own messaging address, talks to your contacts, and extends itself with installable skills.

## What it can do (all working today)

- 📞 **Calls & texts** — TTS phone calls and SMS via Android intents (Twilio scaffolds for full two-way)
- 💬 **Its own identity** — self-registered XMPP address (`fable-s25@yax.im`); anyone can message it
- 🧠 **Real AI replies** — inbound messages answered by Claude with per-sender conversation memory, all traffic through a local audit proxy
- 📒 **Persistent memory** — learns your preferences across sessions (`~/.fable/memory.md`)
- 🔌 **Skills system** — manifest-described capabilities, installable from a git registry:

```
$ skill list
NAME                   VERSION    DESCRIPTION
boot-persist           0.1.0      Start Fable services at device boot.
send-text              0.1.0      Send an SMS.
tts-call               0.1.0      Place a phone call and speak a message via TTS.
xmpp-agent-bridge      0.1.0      AI-powered chat daemon with per-sender memory.
...

$ skill install tts-call --registry https://github.com/you/your-registry.git
Installing: tts-call v0.1.0
  permissions: [dialer, audio]
  installed -> ~/.fable/skills/tts-call/
```

- 🔄 **Survives reboots** — boot-persist skill restarts the proxy + chat bridge via Termux:Boot
- 🔐 **Auditable** — every model request/response logged locally (SOC 2-aligned; see PRD.md)

## Quick start

```bash
git clone <this repo> && cd opencodeprojects
cp .env.example .env   # add your ANTHROPIC_API_KEY
./bootstrap.sh         # installs opencode, verifies key, starts audit proxy
bin/fable              # talk to your agent
```

See `PRD-pocket-agent.md` for the roadmap (skill registry, agent-to-agent messaging).

## Architecture

```
You ⇄ fable (opencode TUI) ──┐
Contacts ⇄ XMPP bridge ──────┼── audit proxy ── Anthropic API
                             │
~/.fable/: memory.md · sessions/ · skills/ · xmpp-inbox.log
```

Built incrementally by the agent itself, on the phone, in conversation. Each capability
was added because a real need came up — then saved as a skill so it never has to be
figured out twice.
