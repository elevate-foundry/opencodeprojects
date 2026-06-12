#!/usr/bin/env python3
"""Fable audit proxy: local reverse proxy in front of api.anthropic.com.

Captures every request/response (and tool_use/tool_result blocks within them)
to an append-only, hash-chained, secret-redacted JSONL audit log.
Stdlib only. Python >= 3.8.
"""
import argparse
import gzip
import hashlib
import html as html_mod
import http.client
import http.server
import json
import os
import re
import socket
import socketserver
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote_plus

UPSTREAM_HOST = "api.anthropic.com"
SECRET_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")
REDACTED = "sk-ant-***REDACTED***"
SENSITIVE_HEADERS = {"x-api-key", "authorization", "cookie", "set-cookie"}
HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "te", "trailer",
               "proxy-authorization", "proxy-authenticate", "upgrade", "host",
               "content-length", "accept-encoding"}
MAX_LOGGED_BODY = 10 * 1024 * 1024  # 10 MiB per body in the log

AUDIT_DIR = Path(os.environ.get("FABLE_AUDIT_DIR", str(Path.home() / ".fable" / "audit")))
STRICT = os.environ.get("FABLE_AUDIT_STRICT", "0") == "1"
RETENTION_DAYS = int(os.environ.get("FABLE_AUDIT_RETENTION_DAYS", "365"))

# --- Key setup state ---
# ENV_FILE is set via --env-file flag; key_ready is an Event signalled once
# a valid ANTHROPIC_API_KEY is available (either from env or via /setup).
ENV_FILE = None  # set in main()
KEY_RE = re.compile(r"^sk-ant-[A-Za-z0-9_\-]{20,}$")
key_ready = threading.Event()

SETUP_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fable &mdash; API Key Setup</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f172a; color: #e2e8f0;
    display: flex; align-items: center; justify-content: center;
    min-height: 100dvh; margin: 0; padding: 1rem;
  }
  .card {
    background: #1e293b; border-radius: 1rem; padding: 2rem;
    max-width: 420px; width: 100%; box-shadow: 0 4px 24px rgba(0,0,0,.4);
  }
  h1 { margin: 0 0 .25rem; font-size: 1.5rem; color: #f8fafc; }
  .sub { color: #94a3b8; font-size: .875rem; margin-bottom: 1.5rem; }
  label { display: block; font-size: .875rem; color: #cbd5e1; margin-bottom: .375rem; }
  input[type="password"], input[type="text"] {
    width: 100%; padding: .75rem 1rem; border-radius: .5rem;
    border: 1px solid #334155; background: #0f172a; color: #f1f5f9;
    font-size: 1rem; font-family: monospace; outline: none;
    transition: border-color .15s;
  }
  input:focus { border-color: #6366f1; }
  .toggle { font-size: .75rem; color: #6366f1; cursor: pointer; margin-top: .25rem; display: inline-block; }
  .error { color: #f87171; font-size: .8125rem; min-height: 1.25rem; margin-top: .5rem; }
  button {
    margin-top: 1rem; width: 100%; padding: .75rem;
    background: #6366f1; color: #fff; font-size: 1rem; font-weight: 600;
    border: none; border-radius: .5rem; cursor: pointer;
    transition: background .15s;
  }
  button:hover { background: #4f46e5; }
  button:disabled { background: #334155; cursor: not-allowed; }
  .info { margin-top: 1.25rem; font-size: .75rem; color: #64748b; line-height: 1.5; }
  .info a { color: #818cf8; }
  .success { text-align: center; }
  .success h2 { color: #34d399; margin-bottom: .5rem; }
</style>
</head>
<body>
<div class="card" id="form-card">
  <h1>Fable</h1>
  <p class="sub">Paste your Anthropic API key to finish setup.</p>
  <form id="keyform" method="POST" action="/setup" autocomplete="off">
    <label for="key">API Key</label>
    <input type="password" id="key" name="key" placeholder="sk-ant-..." autofocus required>
    <span class="toggle" onclick="toggleVis()">show</span>
    <div class="error" id="err"></div>
    <button type="submit" id="btn">Save &amp; Continue</button>
  </form>
  <div class="info">
    Your key stays on this device. It is written to <code>.env</code> (mode 0600, gitignored)
    and never leaves your machine except to <code>api.anthropic.com</code>.<br>
    Get a key at <a href="https://console.anthropic.com/settings/keys" target="_blank">console.anthropic.com</a>.
  </div>
</div>
<div class="card success" id="success-card" style="display:none">
  <h2>Key saved &#x2714;</h2>
  <p>Fable is starting. You can close this tab.</p>
</div>
<script>
function toggleVis() {
  const inp = document.getElementById('key');
  const tog = document.querySelector('.toggle');
  if (inp.type === 'password') { inp.type = 'text'; tog.textContent = 'hide'; }
  else { inp.type = 'password'; tog.textContent = 'show'; }
}
document.getElementById('keyform').addEventListener('submit', async (e) => {
  e.preventDefault();
  const key = document.getElementById('key').value.trim();
  const err = document.getElementById('err');
  const btn = document.getElementById('btn');
  if (!/^sk-ant-[A-Za-z0-9_\\-]{20,}$/.test(key)) {
    err.textContent = 'Key must start with sk-ant- and be at least 28 characters.';
    return;
  }
  btn.disabled = true; btn.textContent = 'Saving\u2026'; err.textContent = '';
  try {
    const resp = await fetch('/setup', {
      method: 'POST',
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: 'key=' + encodeURIComponent(key),
    });
    const data = await resp.json();
    if (data.ok) {
      document.getElementById('form-card').style.display = 'none';
      document.getElementById('success-card').style.display = 'block';
    } else {
      err.textContent = data.error || 'Unknown error';
      btn.disabled = false; btn.textContent = 'Save & Continue';
    }
  } catch (ex) {
    err.textContent = 'Network error: ' + ex.message;
    btn.disabled = false; btn.textContent = 'Save & Continue';
  }
});
</script>
</body>
</html>
"""


def _write_env_key(key):
    """Write ANTHROPIC_API_KEY to the .env file (upsert)."""
    env_path = ENV_FILE
    if not env_path:
        return
    lines = []
    replaced = False
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("ANTHROPIC_API_KEY="):
                    lines.append(f"ANTHROPIC_API_KEY={key}\n")
                    replaced = True
                else:
                    lines.append(line)
    if not replaced:
        lines.append(f"ANTHROPIC_API_KEY={key}\n")
    with open(env_path, "w") as f:
        f.writelines(lines)
    os.chmod(env_path, 0o600)


def _check_key_ready():
    """Return True if ANTHROPIC_API_KEY is set and not a placeholder."""
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(k) and k != "sk-ant-your-key-here" and KEY_RE.match(k)


def redact(text):
    return SECRET_RE.sub(REDACTED, text)


def redact_headers(headers):
    out = {}
    for k, v in headers.items():
        out[k] = "***REDACTED***" if k.lower() in SENSITIVE_HEADERS else redact(v)
    return out


class AuditLog:
    """Append-only JSONL log with a SHA-256 hash chain and daily rotation."""

    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)
        self.lock = threading.Lock()
        self.chain_file = self.dir / ".chain"
        self.prev_hash = self.chain_file.read_text().strip() if self.chain_file.exists() else "0" * 64

    def _current_file(self):
        return self.dir / f"audit-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"

    def write(self, event_type, **fields):
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event_type": event_type,
            "actor": {"user": os.environ.get("USER", "unknown"),
                      "hostname": socket.gethostname()},
        }
        event.update(fields)
        with self.lock:
            event["prev_hash"] = self.prev_hash
            payload = json.dumps(event, sort_keys=True, ensure_ascii=False)
            event["hash"] = hashlib.sha256((self.prev_hash + payload).encode()).hexdigest()
            line = json.dumps(event, sort_keys=True, ensure_ascii=False)
            path = self._current_file()
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                os.chmod(path, 0o600)
                self.prev_hash = event["hash"]
                self.chain_file.write_text(self.prev_hash)
            except OSError:
                if STRICT:
                    raise
        return event["event_id"]

    def rotate(self):
        """Gzip yesterday-and-older logs; delete only past retention."""
        today = f"audit-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        for p in sorted(self.dir.glob("audit-*.jsonl")):
            if p.name != today:
                gz = p.with_suffix(".jsonl.gz")
                with open(p, "rb") as src, gzip.open(gz, "wb") as dst:
                    dst.write(src.read())
                os.chmod(gz, 0o600)
                p.unlink()
        for p in self.dir.glob("audit-*.jsonl.gz"):
            try:
                stamp = datetime.strptime(p.name[6:16], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if stamp < cutoff:
                    p.unlink()
            except ValueError:
                pass


AUDIT = AuditLog(AUDIT_DIR)


def parse_body_for_log(raw):
    """Return (logged_body, parsed_json_or_None). Truncates oversized bodies."""
    text = raw[:MAX_LOGGED_BODY].decode("utf-8", errors="replace")
    if len(raw) > MAX_LOGGED_BODY:
        text += f"...[truncated {len(raw) - MAX_LOGGED_BODY} bytes]"
    text = redact(text)
    try:
        return text, json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text, None


def extract_tool_events(session_id, request_json, response_json, sse_text):
    """Emit tool_call / tool_result events found in message bodies or SSE."""
    def scan_blocks(blocks, direction):
        for b in blocks or []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                AUDIT.write("tool_call", session_id=session_id, direction=direction,
                            tool={"name": b.get("name"), "id": b.get("id"),
                                  "input": b.get("input")})
            elif b.get("type") == "tool_result":
                AUDIT.write("tool_result", session_id=session_id, direction=direction,
                            tool={"tool_use_id": b.get("tool_use_id"),
                                  "is_error": b.get("is_error", False),
                                  "content": b.get("content")})

    if request_json:
        for msg in request_json.get("messages", []):
            content = msg.get("content")
            if isinstance(content, list):
                scan_blocks(content, "request")
    if response_json:
        scan_blocks(response_json.get("content"), "response")
    if sse_text:
        # reconstruct tool_use blocks from streaming events
        current = None
        for line in sse_text.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except (json.JSONDecodeError, ValueError):
                continue
            t = ev.get("type")
            if t == "content_block_start" and ev.get("content_block", {}).get("type") == "tool_use":
                cb = ev["content_block"]
                current = {"name": cb.get("name"), "id": cb.get("id"), "input_json": ""}
            elif t == "content_block_delta" and current is not None:
                current["input_json"] += ev.get("delta", {}).get("partial_json", "")
            elif t == "content_block_stop" and current is not None:
                try:
                    parsed = json.loads(current["input_json"]) if current["input_json"] else {}
                except (json.JSONDecodeError, ValueError):
                    parsed = current["input_json"]
                AUDIT.write("tool_call", session_id=session_id, direction="response_stream",
                            tool={"name": current["name"], "id": current["id"], "input": parsed})
                current = None


def _extract_sse_usage(sse_text):
    """Extract and merge usage from SSE events (message_start + message_delta).

    Anthropic streaming sends:
      - message_start: {"type": "message_start", "message": {"usage": {"input_tokens": N, "cache_read_input_tokens": N, "cache_creation_input_tokens": N}}}
      - message_delta: {"type": "message_delta", "usage": {"output_tokens": N}}
    We merge both into one dict matching the non-streaming usage format.
    """
    usage = {}
    for line in sse_text.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            ev = json.loads(line[5:].strip())
        except (json.JSONDecodeError, ValueError):
            continue
        t = ev.get("type")
        if t == "message_start":
            msg_usage = ev.get("message", {}).get("usage", {})
            usage.update(msg_usage)
        elif t == "message_delta":
            delta_usage = ev.get("usage", {})
            usage.update(delta_usage)
    return usage or None


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "FableAuditProxy/1.0"

    def log_message(self, fmt, *args):  # silence default stderr access log
        pass

    def _audit_writable(self):
        try:
            AUDIT.dir.mkdir(parents=True, exist_ok=True)
            test = AUDIT.dir / ".wtest"
            test.write_text("")
            test.unlink()
            return True
        except OSError:
            return False

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status, html_text):
        body = html_text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            self._send_json(200, {
                "ok": True,
                "audit_dir": str(AUDIT.dir),
                "key_configured": key_ready.is_set(),
            })
            return
        if self.path == "/setup":
            if key_ready.is_set():
                self._send_html(200, '<html><body style="background:#0f172a;color:#34d399;'
                    'display:flex;align-items:center;justify-content:center;'
                    'min-height:100vh;font-family:sans-serif">'
                    '<h1>Fable is already configured &#x2714;</h1></body></html>')
            else:
                self._send_html(200, SETUP_HTML)
            return
        self._proxy()

    def do_POST(self):
        if self.path == "/setup":
            self._handle_setup_post()
            return
        self._proxy()

    def _handle_setup_post(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode()
        key = ""
        for part in raw.split("&"):
            if part.startswith("key="):
                key = unquote_plus(part[4:]).strip()
        if not KEY_RE.match(key):
            self._send_json(400, {"ok": False,
                "error": "Invalid key format. Must start with sk-ant- and be 28+ chars."})
            return
        try:
            _write_env_key(key)
        except OSError as exc:
            self._send_json(500, {"ok": False,
                "error": f"Failed to write .env: {html_mod.escape(str(exc))}"})
            return
        # Set in current process so the proxy can immediately forward requests
        os.environ["ANTHROPIC_API_KEY"] = key
        key_ready.set()
        AUDIT.write("key_setup", method="browser", env_file=str(ENV_FILE))
        self._send_json(200, {"ok": True})

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def _proxy(self):
        if STRICT and not self._audit_writable():
            self.send_error(503, "audit log unwritable (FABLE_AUDIT_STRICT=1)")
            return

        # Normalize: some SDKs omit /v1/ when baseURL is set
        if self.path.startswith("/messages") or self.path.startswith("/complete"):
            self.path = "/v1" + self.path

        session_id = self.headers.get("x-fable-session", str(uuid.uuid4()))
        length = int(self.headers.get("Content-Length") or 0)
        req_raw = self.rfile.read(length) if length else b""
        req_text, req_json = parse_body_for_log(req_raw)
        model = (req_json or {}).get("model")
        is_stream = bool((req_json or {}).get("stream"))

        AUDIT.write("api_request", session_id=session_id, model=model,
                    http={"method": self.command, "path": self.path},
                    headers=redact_headers(dict(self.headers)),
                    request=req_text)

        start = time.monotonic()
        try:
            conn = http.client.HTTPSConnection(UPSTREAM_HOST, timeout=600)
            fwd_headers = {k: v for k, v in self.headers.items()
                           if k.lower() not in HOP_HEADERS}
            fwd_headers["Host"] = UPSTREAM_HOST
            fwd_headers["Accept-Encoding"] = "identity"
            if req_raw:
                fwd_headers["Content-Length"] = str(len(req_raw))
            conn.request(self.command, self.path, body=req_raw or None, headers=fwd_headers)
            resp = conn.getresponse()
        except OSError as exc:
            AUDIT.write("api_response", session_id=session_id, model=model,
                        http={"method": self.command, "path": self.path, "status": 0},
                        error=str(exc))
            self.send_error(502, "upstream connection failed")
            return

        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() in HOP_HEADERS | {"content-length"}:
                continue
            self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()

        chunks = []
        try:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                if is_stream:
                    self.wfile.flush()
                chunks.append(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            conn.close()
            self.close_connection = True

        resp_raw = b"".join(chunks)
        resp_text, resp_json = parse_body_for_log(resp_raw)
        latency_ms = int((time.monotonic() - start) * 1000)

        # --- extract usage (non-streaming: top-level; streaming: from SSE events) ---
        usage = (resp_json or {}).get("usage")
        sse_text = resp_text if is_stream else None
        if is_stream and sse_text:
            usage = _extract_sse_usage(sse_text)

        AUDIT.write("api_response", session_id=session_id, model=model,
                    http={"method": self.command, "path": self.path, "status": resp.status},
                    headers=redact_headers(dict(resp.getheaders())),
                    usage=usage, latency_ms=latency_ms, stream=is_stream,
                    response=resp_text)
        extract_tool_events(session_id, req_json, resp_json, sse_text)


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def rotation_loop():
    while True:
        try:
            AUDIT.rotate()
        except OSError:
            pass
        time.sleep(3600)


def main():
    global ENV_FILE
    parser = argparse.ArgumentParser(description="Fable audit proxy")
    parser.add_argument("--port", type=int, default=int(os.environ.get("FABLE_PROXY_PORT", "8377")))
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--env-file", default=None,
                        help="Path to .env file for key setup (enables /setup endpoint)")
    parser.add_argument("--open-setup", action="store_true",
                        help="Auto-open /setup in browser if no API key is configured")
    args = parser.parse_args()

    ENV_FILE = args.env_file

    # Check if key is already available
    if _check_key_ready():
        key_ready.set()

    AUDIT.write("bootstrap_phase", phase="proxy_start",
                config={"port": args.port, "strict": STRICT,
                        "retention_days": RETENTION_DAYS, "audit_dir": str(AUDIT.dir),
                        "key_configured": key_ready.is_set()})
    threading.Thread(target=rotation_loop, daemon=True).start()
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"fable audit proxy listening on {args.bind}:{args.port} -> https://{UPSTREAM_HOST}")

    if not key_ready.is_set() and args.open_setup:
        setup_url = f"http://localhost:{args.port}/setup"
        print(f"  No API key configured. Open {setup_url} to enter your key.")
        try:
            subprocess.Popen(["termux-open-url", setup_url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            pass  # not on Termux

    server.serve_forever()


if __name__ == "__main__":
    main()
