# PRD: Fable Bootstrap — One-Command opencode + Anthropic Provisioning with SOC 2 Audit Logging

| Field | Value |
|---|---|
| Status | Draft v1.0 |
| Owner | owner |
| Last updated | 2026-06-12 |
| Source material | `build.md` (prompt architecture & caching notes) |

---

## 1. Problem Statement

Setting up opencode as an Anthropic-backed coding agent ("Fable") currently requires manual,
error-prone steps: installing the correct opencode binary for the host platform, exporting
`ANTHROPIC_API_KEY`, validating the key actually works, wiring opencode's provider config,
and assembling the cacheable system-prompt / repo-manifest / session-preflight layers
described in `build.md`. There is also no audit trail of model traffic, which blocks
SOC 2 readiness.

## 2. Goals

1. **Single command** (`./bootstrap.sh`, alias `fable-up`) provisions the entire system
   from a clean machine to a working opencode ↔ Anthropic session.
2. **Platform-aware install**: detect OS + architecture + form factor and download the
   correct opencode release, skipping download if a valid binary already exists.
3. **Credential verification**: confirm `ANTHROPIC_API_KEY` is present in `.env`
   (never echoed), well-formed, and accepted by the Anthropic API.
4. **Warmup**: issue a minimal real completion against the configured Anthropic model(s)
   to prime auth, measure latency, and (optionally) seed the prompt cache with the
   stable system prompt + repo manifest per `build.md`.
5. **Automatic connection**: generate/merge opencode config so the Anthropic provider is
   selected with no interactive auth step.
6. **SOC 2-aligned audit logging**: every API request, response, and tool call is logged
   to tamper-evident, append-only, secret-redacted local logs.

## 3. Non-Goals

- iOS support (no opencode build exists; out of scope).
- Managing multiple model providers (Anthropic only in v1).
- Remote/centralized log shipping (v1 is local; SIEM export is a v2 hook).
- Being a SOC 2 *certification*. This delivers SOC 2-aligned logging controls
  (CC6.x, CC7.x); certification requires org-level audit work.
- Key provisioning. The user supplies `.env` with `ANTHROPIC_API_KEY`.

## 4. Users

- **Primary**: the repo owner running Fable/opencode across laptop, desktop, and
  Android (Termux) devices.
- **Secondary**: a future auditor reviewing the audit log trail.

## 5. Requirements

### 5.1 FR-1: Single-command bootstrap

- `./bootstrap.sh` is idempotent: safe to re-run; each phase no-ops if already satisfied.
- Phases run in order, fail fast, and print a per-phase ✓/✗ summary:
  1. Platform detection
  2. opencode install/verify
  3. `.env` / key verification
  4. Anthropic warmup call
  5. opencode ↔ Anthropic config wiring
  6. Audit-logging proxy start + health check
  7. Final smoke test (opencode invocation through the proxy)
- Exit code `0` only if all phases pass. Non-zero exit prints the failing phase and a
  remediation hint.
- Flags: `--check` (dry run, report only), `--force-download`, `--no-warmup`, `--verbose`.

### 5.2 FR-2: Platform detection & opencode install

- Detect via `uname -s` / `uname -m` (and Termux markers / `$PREFIX` for Android):

  | Detected | Target artifact |
  |---|---|
  | Linux x86_64 | `opencode-linux-x64` |
  | Linux aarch64 (desktop/SBC) | `opencode-linux-arm64` |
  | Android/Termux aarch64 | `opencode-linux-arm64` (Termux notes applied) |
  | macOS arm64 | `opencode-darwin-arm64` |
  | macOS x86_64 | `opencode-darwin-x64` |
  | Windows (Git Bash/WSL) | WSL → linux path; native Windows out of scope v1 |
  | Anything else | Hard fail with message |

- Form-factor hint (mobile vs laptop vs desktop) is recorded in session preflight
  (battery/chassis heuristics: `/sys/class/power_supply`, Termux env), used for
  logging context only — not for artifact selection beyond OS/arch.
- If `opencode` is already on `PATH` or at `~/.local/bin/opencode` and
  `opencode --version` succeeds, skip download (unless `--force-download`).
- Download from official opencode GitHub releases over HTTPS; verify checksum
  (published SHA256) before install; install to `~/.local/bin/opencode` with `0755`.
- Record installed version in bootstrap state file (`~/.fable/state.json`).

### 5.3 FR-3: Credential verification

- Load `.env` from repo root. Required: `ANTHROPIC_API_KEY`.
- Validation steps:
  1. Present and non-empty.
  2. Shape check: starts with `sk-ant-`.
  3. Live check: lightweight authenticated API call (e.g., `GET /v1/models` or a
     1-token message) — confirms the key is active, not just well-formed.
- The key value is **never** printed, logged, or written anywhere outside `.env`
  and process env. All logs show `sk-ant-***REDACTED***`.
- `.env` must be in `.gitignore`; bootstrap adds it if missing and warns if `.env`
  is already tracked by git.
- `.env` file mode tightened to `0600` if looser.

### 5.4 FR-4: Warmup call

- After key verification, send a minimal real completion (`max_tokens` ≤ 16) to the
  default model (configurable, default `claude-sonnet-4-5`).
- Capture and report: model id, HTTP status, time-to-first-byte, total latency,
  input/output token counts.
- Optional `--prime-cache`: send the stable system prompt + repo manifest (generated
  per `build.md` §"repo manifest") with `cache_control` breakpoints so the first real
  opencode session gets cache hits. Cache boundary rules from `build.md` apply:
  nothing dynamic (timestamps, git status, cwd, task text) before the breakpoint.
- Warmup failure (auth error, model not found, network) fails the bootstrap with the
  exact API error category (status code + Anthropic error type), never the raw key.

### 5.5 FR-5: Automatic opencode ↔ Anthropic connection

- Generate or merge (never clobber unrelated settings) opencode config
  (`opencode.json` in repo and/or `~/.config/opencode/`) so that:
  - Provider = Anthropic, model = configured default.
  - Auth resolves from `ANTHROPIC_API_KEY` env var — no `opencode auth login`
    interactive step required.
  - Anthropic base URL points at the **local audit proxy** (FR-6) so all traffic is
    captured: `ANTHROPIC_BASE_URL=http://127.0.0.1:<proxy_port>`.
- Install the layered prompt assets from `build.md`:
  - Stable system prompt (Fable operating contract, security, git/patch/test/cost
    rules) → `prompts/system.md`, referenced via opencode instructions/rules config.
  - `scripts/preflight.sh` (session preflight: user, host, pwd, git root/branch/
    commit/dirty, top-level files, manifests) — productionized version of the
    `/tmp/fable-preflight.sh` draft in `build.md`.
  - `scripts/repo-manifest.sh` → cached per commit at
    `~/.fable/cache/manifest-<commit>.txt`.
- Smoke test: run a trivial non-interactive opencode command and confirm (a) it
  succeeds and (b) the request appears in the audit log.

### 5.6 FR-6: SOC 2-aligned audit logging

**Mechanism**: a local logging reverse proxy (single small daemon, started by
bootstrap, supervised with a pidfile + health endpoint) sits between opencode and
`api.anthropic.com`. opencode points at the proxy via base URL override. This
guarantees capture of **all** request/response traffic regardless of opencode
internals. Tool-call activity is captured two ways: (a) tool_use / tool_result blocks
appear inside the proxied message bodies; (b) opencode's own session/log output is
tailed into the same audit stream for local tool execution detail (command lines,
file paths, exit codes).

**What is logged** (JSONL, one event per line):

| Field | Notes |
|---|---|
| `event_id` | UUIDv7 |
| `timestamp` | UTC, RFC 3339, ms precision |
| `event_type` | `api_request`, `api_response`, `tool_call`, `tool_result`, `auth_check`, `bootstrap_phase`, `config_change` |
| `session_id` | opencode session correlation id |
| `actor` | OS user + hostname + form factor |
| `model` | model id |
| `request` / `response` | Full body, after redaction |
| `tool` | Tool name, arguments, result, exit code (for tool events) |
| `usage` | Input/output/cache tokens, latency ms |
| `http` | Method, path, status |
| `prev_hash` / `hash` | SHA-256 hash chain for tamper evidence |

**Controls** (mapping to SOC 2 Trust Services Criteria):

- **CC6.1 / CC6.6 (access)**: log directory `~/.fable/audit/` mode `0700`, files `0600`;
  owned by the invoking user.
- **CC7.2 (monitoring)**: complete capture of all API and tool activity; bootstrap
  smoke test asserts log capture is live before declaring success.
- **CC7.3 (integrity)**: append-only JSONL with per-event SHA-256 hash chaining;
  `fable-audit verify` recomputes the chain and reports any tampering. Where the
  filesystem supports it, `chattr +a` is applied.
- **CC6.7 (confidentiality)**: redaction layer strips `x-api-key` / `authorization`
  headers and any `sk-ant-*` patterns from all logged bodies before write.
- **Retention**: daily rotation, gzip after 24h, retained ≥ 365 days (configurable);
  rotation never deletes within the retention window.
- **Clock**: timestamps always UTC; NTP sync status recorded in each bootstrap run.
- **Fail-closed option**: `FABLE_AUDIT_STRICT=1` makes the proxy refuse to forward
  traffic if the audit log is unwritable (default v1: warn loudly, continue).

### 5.7 Configuration surface

`.env` (gitignored):

```
ANTHROPIC_API_KEY=sk-ant-...        # required
FABLE_MODEL=claude-sonnet-4-5       # optional
FABLE_PROXY_PORT=8377               # optional
FABLE_AUDIT_DIR=~/.fable/audit      # optional
FABLE_AUDIT_RETENTION_DAYS=365      # optional
FABLE_AUDIT_STRICT=0                # optional
```

## 6. Deliverables

| # | Artifact | Description |
|---|---|---|
| 1 | `bootstrap.sh` | Single-command entry point (POSIX-ish bash, runs on Linux/macOS/Termux) |
| 2 | `scripts/preflight.sh` | Session preflight (from `build.md`) |
| 3 | `scripts/repo-manifest.sh` | Per-commit cacheable repo manifest (from `build.md`) |
| 4 | `prompts/system.md` | Stable Fable system prompt (operating contract from `build.md`) |
| 5 | `proxy/` | Audit logging proxy daemon + redaction + hash chain |
| 6 | `fable-audit` | CLI: `tail`, `verify`, `export`, `rotate` |
| 7 | `opencode.json` | Generated/merged opencode provider config |
| 8 | `.env.example` | Template with all variables documented |
| 9 | `README.md` | Quickstart: `cp .env.example .env && ./bootstrap.sh` |

## 7. Acceptance Criteria

1. Clean Linux x64 machine + valid `.env` → `./bootstrap.sh` exits 0; `opencode` is
   installed and answers `--version`; warmup metrics printed.
2. Re-running `./bootstrap.sh` performs no downloads and exits 0 in < 10s
   (idempotency).
3. Wrong/empty `ANTHROPIC_API_KEY` → bootstrap fails at phase 3 with a clear message;
   the key value appears nowhere in output or logs.
4. On linux-arm64 / Termux, the arm64 artifact is selected automatically.
5. Running one opencode task produces audit events covering: the outbound API request,
   the API response, and every tool call/result — verifiable via `fable-audit tail`.
6. `fable-audit verify` passes on an untouched log and fails after any byte of a
   logged event is modified.
7. No occurrence of the raw API key in any file under `~/.fable/` (grep check is part
   of the bootstrap smoke test).
8. With `--prime-cache`, the second warmup call reports cache-read tokens > 0.

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| opencode release naming/URL changes | Pin a tested version in `state.json`; checksum verify; `--force-download` to upgrade |
| Proxy adds latency / becomes SPOF | Localhost hop is ~sub-ms; health check + auto-restart in bootstrap; strict mode optional |
| opencode config schema drift | Merge via documented config keys only; smoke test catches breakage at bootstrap time |
| Log volume (full bodies) | Gzip rotation; bodies are text; est. < 100 MB/day heavy use |
| Termux quirks (no systemd, paths) | Detect `$PREFIX`; nohup-based proxy supervision fallback |
| Secrets leak via tool output inside bodies | Redaction layer scans bodies, not just headers, for `sk-ant-*` and configured secret patterns |

## 9. Milestones

1. **M1 — Bootstrap core**: platform detect, install, key verify, warmup (FR-1–FR-4).
2. **M2 — Wiring**: opencode config merge, prompt assets, preflight/manifest scripts (FR-5).
3. **M3 — Audit**: proxy, redaction, hash chain, `fable-audit` CLI, retention (FR-6).
4. **M4 — Hardening**: Termux/macOS matrix testing, strict mode, cache priming, README.

## 10. Open Questions

1. Default model — confirm `claude-sonnet-4-5` vs an Opus-class default for Fable.
2. Should v1 strict mode (fail-closed audit) be the default, or warn-and-continue?
3. Is Windows-native (non-WSL) support needed at all, or is WSL sufficient?
4. Retention target: is 365 days correct for your SOC 2 program, or does your auditor
   require a different window?
