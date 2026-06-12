# Quickstart — Linux

Get Fable (opencode + Anthropic + SOC 2 audit logging) running in under 2 minutes.

## Prerequisites

- **Linux** x86_64 or arm64 (Ubuntu, Debian, Fedora, Arch, Termux — anything with bash)
- **Python 3.8+** (`python3 --version`)
- **curl**, **unzip** (pre-installed on most distros)
- **git** (optional but recommended)
- An **Anthropic API key** (`sk-ant-...`) — get one at https://console.anthropic.com/settings/keys

## 1. Clone and enter the repo

```bash
git clone https://github.com/YOUR_ORG/opencodeprojects.git
cd opencodeprojects
```

## 2. Add your API key

```bash
cp .env.example .env
nano .env   # paste your key on the ANTHROPIC_API_KEY= line
```

The file should look like:

```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxx
```

> `.env` is gitignored. Bootstrap will `chmod 600` it automatically.

## 3. Run bootstrap

```bash
./bootstrap.sh
```

That's it. Bootstrap runs 7 phases:

```
✓ platform detection (linux-x64, laptop)
✓ opencode present (1.14.28)            # or downloads + SHA256-verifies it
✓ credentials verified                   # shape + live API check, key never printed
✓ warmup (claude-sonnet-4-5)            # real completion, reports latency
✓ opencode wired to anthropic via audit proxy
✓ audit proxy started                    # 127.0.0.1:8377, all traffic logged
✓ smoke test                             # end-to-end, hash chain verified
```

## 4. Use opencode

```bash
opencode
```

Every request and response now flows through the local audit proxy and is logged to `~/.fable/audit/`.

## Common flags

| Flag | Effect |
|---|---|
| `--check` | Dry run — report what *would* happen, change nothing |
| `--force-download` | Re-download opencode even if already installed |
| `--no-warmup` | Skip the warmup API call |
| `--prime-cache` | Seed the Anthropic prompt cache with the system prompt + repo manifest |
| `--verbose` | Extra detail per phase |

## Verify the audit log

```bash
./bin/fable-audit tail          # last 20 events
./bin/fable-audit verify        # recompute SHA-256 hash chain
./bin/fable-audit tail -n 5     # last 5 events
```

## Re-running is safe

Bootstrap is idempotent. If opencode is already installed and the proxy is already running, it skips those steps and finishes in ~3 seconds:

```bash
./bootstrap.sh --no-warmup      # fast re-check
```

## Termux (Android)

Same steps. Bootstrap detects `$TERMUX_VERSION` / `$PREFIX` and pulls the `linux-arm64` binary. Install `python` and `curl` first:

```bash
pkg install python curl unzip git
```

## Stop the proxy

```bash
kill "$(cat ~/.fable/proxy.pid)"
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `python3: command not found` | `sudo apt install python3` (or `pkg install python` on Termux) |
| `unzip: command not found` | `sudo apt install unzip` |
| Phase 3 fails: "malformed key" | Key must start with `sk-ant-`. Check `.env` for trailing whitespace. |
| Phase 3 fails: "HTTP 401" | Key is expired or revoked. Generate a new one at console.anthropic.com. |
| Phase 6 fails: health check | Port 8377 in use? Set `FABLE_PROXY_PORT=8378` in `.env`. |
| `opencode` not found after bootstrap | Add `~/.local/bin` to PATH: `export PATH="$HOME/.local/bin:$PATH"` |

## What's next

- **Full spec**: [PRD.md](PRD.md)
- **Prompt architecture**: [build.md](build.md)
- **All config options**: [.env.example](.env.example)
