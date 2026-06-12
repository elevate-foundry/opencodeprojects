# Fable Bootstrap

One command provisions opencode + Anthropic ("Fable") with SOC 2-aligned audit logging.
Full spec: [PRD.md](PRD.md). Prompt architecture notes: [build.md](build.md).

## Quickstart

```bash
cp .env.example .env       # add your ANTHROPIC_API_KEY
./bootstrap.sh
opencode
```

`bootstrap.sh` is idempotent. It will:

1. Detect OS/arch/form-factor (Linux x64/arm64, macOS, Android/Termux).
2. Download the matching opencode release (skipped if already installed; SHA256-verified).
3. Verify `ANTHROPIC_API_KEY` is present, well-formed, and live (key is never printed/logged).
4. Run a warmup completion and report latency + token usage.
5. Write/merge `opencode.json` so opencode talks to Anthropic through the local audit proxy.
6. Start the audit proxy (`127.0.0.1:8377` by default) with a health check.
7. Smoke-test end-to-end: proxied request, audit capture, secret-leak grep, hash-chain verify.

Flags: `--check` (dry run), `--force-download`, `--no-warmup`, `--prime-cache`, `--verbose`.

## Audit logging

All API requests, responses, and tool calls flow through `proxy/audit_proxy.py` and land in
`~/.fable/audit/audit-YYYY-MM-DD.jsonl`:

- Append-only JSONL, per-event SHA-256 hash chain (tamper-evident).
- `x-api-key`/`authorization` headers and any `sk-ant-*` strings redacted before write.
- Directory `0700`, files `0600`, daily rotation, gzip after 24h, 365-day retention.
- `FABLE_AUDIT_STRICT=1` makes the proxy fail closed if the log is unwritable.

```bash
./bin/fable-audit tail -n 50    # recent events
./bin/fable-audit verify        # recompute hash chain; exits 1 on tamper
./bin/fable-audit export --out audit-export.jsonl
./bin/fable-audit rotate
```

> Note: this delivers SOC 2-aligned logging controls (CC6.x/CC7.x). SOC 2 certification
> itself requires organization-level audit work.

## Layout

| Path | Purpose |
|---|---|
| `bootstrap.sh` | Single-command bootstrap (alias it as `fable-up`) |
| `proxy/audit_proxy.py` | Logging reverse proxy (Python 3 stdlib, no deps) |
| `bin/fable-audit` | Audit log CLI |
| `prompts/system.md` | Stable Fable system prompt (cacheable, used as opencode instructions) |
| `scripts/preflight.sh` | Dynamic session facts (injected per session, never cached) |
| `scripts/repo-manifest.sh` | Per-commit repo manifest, cached at `~/.fable/cache/` |
| `.env.example` | All configuration variables |

## Configuration

See `.env.example`. Required: `ANTHROPIC_API_KEY`. Optional: `FABLE_MODEL`
(default `claude-sonnet-4-5`), `FABLE_PROXY_PORT`, `FABLE_AUDIT_DIR`,
`FABLE_AUDIT_RETENTION_DAYS`, `FABLE_AUDIT_STRICT`.

## Stopping the proxy

```bash
kill "$(cat ~/.fable/proxy.pid)"
```
