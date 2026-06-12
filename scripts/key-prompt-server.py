#!/usr/bin/env python3
"""Tiny local HTTP server that presents a mobile-friendly form to collect
the Anthropic API key, validates its shape, writes it to .env, and exits.

Stdlib only. Used by bootstrap.sh when no ANTHROPIC_API_KEY is set —
especially useful on Termux where pasting long keys into the terminal is
painful.

Usage:
    python3 scripts/key-prompt-server.py --env-file .env [--port 8378]

The server binds to 0.0.0.0 so the phone's own browser can reach it at
http://localhost:<port>.  It auto-opens the browser on Termux via
`termux-open-url` if available.  Once a valid key is submitted the server
writes .env, prints the key (to stdout, for the caller to capture if
needed), and exits 0.  Ctrl-C or timeout (5 min) exits 1.
"""
import argparse
import html
import http.server
import os
import re
import socketserver
import subprocess
import sys
import threading

KEY_RE = re.compile(r"^sk-ant-[A-Za-z0-9_\-]{20,}$")
TIMEOUT_SECONDS = 300  # 5 minutes

HTML_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fable — API Key Setup</title>
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
  <form id="keyform" method="POST" action="/submit" autocomplete="off">
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
  <h2>Key saved</h2>
  <p>Bootstrap is continuing in the terminal. You can close this tab.</p>
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
  btn.disabled = true; btn.textContent = 'Saving…'; err.textContent = '';
  try {
    const resp = await fetch('/submit', {
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

received_key = None
server_ref = None


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence access log

    def do_GET(self):
        body = HTML_PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        global received_key
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode()
        # parse key= from form body
        key = ""
        for part in raw.split("&"):
            if part.startswith("key="):
                from urllib.parse import unquote_plus
                key = unquote_plus(part[4:]).strip()

        if not KEY_RE.match(key):
            resp = b'{"ok":false,"error":"Invalid key format. Must start with sk-ant- and be 28+ chars."}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        # Write .env
        try:
            env_path = handler_args.env_file
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
        except OSError as exc:
            resp = f'{{"ok":false,"error":"Failed to write .env: {html.escape(str(exc))}"}}'.encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        received_key = key
        resp = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

        # Shut down server after response is sent
        threading.Thread(target=_shutdown, daemon=True).start()


def _shutdown():
    import time
    time.sleep(0.5)
    if server_ref:
        server_ref.shutdown()


class ReusableServer(socketserver.TCPServer):
    allow_reuse_address = True


def main():
    global server_ref, handler_args
    parser = argparse.ArgumentParser(description="Collect Anthropic API key via browser")
    parser.add_argument("--env-file", required=True, help="Path to .env file to write")
    parser.add_argument("--port", type=int, default=8378)
    handler_args = parser.parse_args()

    server_ref = ReusableServer(("0.0.0.0", handler_args.port), Handler)

    # Auto-open browser on Termux
    url = f"http://localhost:{handler_args.port}"
    print(f"  Open {url} in your browser to enter your API key.")
    try:
        subprocess.Popen(["termux-open-url", url],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass  # not on Termux or termux-open-url not installed

    # Timeout: exit 1 after TIMEOUT_SECONDS if no key submitted
    def timeout_handler():
        import time
        time.sleep(TIMEOUT_SECONDS)
        if received_key is None:
            print("\n  Timed out waiting for API key.", file=sys.stderr)
            server_ref.shutdown()

    threading.Thread(target=timeout_handler, daemon=True).start()

    try:
        server_ref.serve_forever()
    except KeyboardInterrupt:
        pass

    if received_key:
        # Print key to stdout so calling script can capture it
        print(received_key)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
