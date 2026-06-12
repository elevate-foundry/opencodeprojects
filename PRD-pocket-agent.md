# PRD: Pocket Agent Kit — A Phone-Native Autonomous Agent Framework

| Field | Value |
|---|---|
| Status | Draft v0.1 |
| Owner | salus-ryan |
| Last updated | 2026-06-12 |
| Builds on | bootstrap.sh (PRD.md), prompts/ architecture, skills/ built 2026-06-12 |

## 1. Problem

Every serious agent framework assumes a server or laptop. Nobody owns the phone,
yet the phone is where identity lives: your SIM, your contacts, your notifications,
your location in the world. Today we proved an agent on Termux can place calls,
send texts, register its own messaging identity (XMPP), receive messages while
idle, authenticate to GitHub via OAuth device flow, and persist memory across
sessions. That was ad-hoc. This PRD turns it into an installable kit.

## 2. Vision

`curl -L pocket-agent.sh | bash` on any Android phone with Termux →
a named agent with persistent memory, a reachable messaging address,
device skills (call/text/notify/TTS), and a skills registry it can
extend itself. "An AI that lives in your phone and remembers you."

## 3. Goals (v1)

1. **One-command install** — extend bootstrap.sh: provision agent home
   (`~/.fable/`), memory, sessions, skills dir, XMPP identity, listener daemon.
2. **Skill manifest standard** — every skill ships `skill.yaml` (name, description,
   triggers, usage, requirements, permissions). Agents discover skills by reading
   manifests, not source.
3. **Skills registry** — a git repo of skills; `skill install <name>` clones,
   verifies requirements (e.g. termux-api present), and symlinks into
   `~/.fable/skills/`. Agents may author and publish skills back.
4. **Reachable identity** — auto-register XMPP address on first boot; listener
   daemon survives reboot (Termux:Boot); inbound messages can wake a full agent
   session (v1: log + notify + auto-ack; v1.5: spawn `fable -p "<msg>"` and reply
   with the answer).
5. **Memory + session continuity** — already working (memory.md, sessions/);
   formalize size limits and pruning.

## 4. Non-Goals (v1)

- iOS (no Termux equivalent).
- Multi-agent orchestration (v2: agents messaging agents over XMPP).
- Hosted/cloud components — everything runs on the phone.
- Marketplace moderation; v1 registry is a curated git repo.

## 5. Skill Manifest Format

```yaml
# skill.yaml
name: tts-call
version: 0.1.0
description: Place a phone call and speak a message via TTS.
entrypoint: tts-call.sh
usage: "tts-call.sh <number> \"<message>\" [delay_seconds]"
triggers: ["call someone", "phone call", "speak to person on phone"]
requirements:
  os: android-termux
  bins: [termux-tts-speak, am]
permissions: [dialer, audio]
interactive: true   # requires user action (tap Call)
```

## 6. Architecture

```
~/.fable/
  memory.md            # long-term learned patterns
  sessions/            # per-session summaries
  skills/<name>/       # skill.yaml + entrypoint (v1 migrates flat scripts)
  identity/            # xmpp jid, password (0600)
  xmpp-inbox.log       # inbound messages
registry (git):  github.com/<org>/pocket-agent-skills
```

## 7. Milestones

- M1: skill.yaml for the 8 existing skills; `skill list/info` command.
- M2: `skill install` from registry repo; requirement checks.
- M3: boot persistence (Termux:Boot) + listener → agent session bridge.
- M4: public registry repo + install one-liner; README/demo video.

## 8. Risks

- Android kills background processes (mitigate: Termux:Boot, wakelock, notification).
- Play Store Termux lacks termux-api perms (document F-Droid path).
- Open XMPP servers may close registration (registry of known-good servers; fallback list).
- Security: skills run arbitrary shell — registry must be curated, manifests
  declare permissions, installer shows them before enabling.

## 9. Success Criteria

A stranger with an Android phone runs one command, names their agent, and within
five minutes: the agent texts them from its own XMPP address, remembers their
name the next day, and installs a new skill on request.
