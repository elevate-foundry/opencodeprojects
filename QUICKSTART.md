# Quickstart

Export your key, then one command:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

```bash
git clone https://github.com/salus-ryan/opencodeprojects.git && cd opencodeprojects && echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" > .env && ./bootstrap.sh
```

That's it. Bootstrap handles everything — Python, opencode, config, audit proxy, smoke test. When it finishes:

```bash
./bin/fable          # launch Fable (assembles dynamic prompt, starts opencode)
```

---

## What bootstrap does (10 phases)

```
✓ cleanup                                # kills stale proxy processes
✓ platform detection (linux-x64, laptop) # also supports macOS, arm64, Termux
✓ python + venv                          # auto-installs python3 if missing
✓ opencode present (1.14.28)             # or downloads + SHA256-verifies it
✓ credentials verified                   # shape + live API check, key never printed
✓ warmup (claude-sonnet-4-5)             # real completion, reports latency + cache stats
✓ dynamic prompt assembled               # layers core + manifest + memory + preflight
✓ opencode wired to anthropic via audit proxy
✓ audit proxy started                    # 127.0.0.1:8377, all traffic logged
✓ smoke test                             # end-to-end, hash chain verified
```

## Common flags

| Flag | Effect |
|---|---|
| `--check` | Dry run — report what *would* happen, change nothing |
| `--force-download` | Re-download opencode even if already installed |
| `--no-warmup` | Skip the warmup API call |
| `--prime-cache` | Seed the Anthropic prompt cache with the system prompt + repo manifest |
| `--verbose` | Extra detail per phase |

## Audit log

```bash
./bin/fable-audit tail          # last 20 events
./bin/fable-audit verify        # recompute SHA-256 hash chain
./bin/fable-audit tokens        # token usage + cost (compare with Anthropic console)
./bin/fable-audit tokens --date 2026-06-12  # filter by date
./bin/fable-audit export --out dump.jsonl   # full export
```

## Re-running is safe

Bootstrap is idempotent. If opencode is already installed and the proxy is already running, it skips those steps and finishes in ~3 seconds:

```bash
./bootstrap.sh --no-warmup      # fast re-check
```

## Termux (Android) — one command

Paste this single command in Termux. It installs deps, clones the repo, and opens a browser page on your phone to paste your API key:

```bash
curl -fsSL https://raw.githubusercontent.com/salus-ryan/opencodeprojects/main/scripts/termux-install.sh | bash
```

That's it. No need to manually create `.env` or type your API key into the terminal — a mobile-friendly web page pops up for you to paste it.

If you prefer to set the key beforehand:

```bash
pkg install python curl git golang
git clone https://github.com/salus-ryan/opencodeprojects.git && cd opencodeprojects
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env && ./bootstrap.sh
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
