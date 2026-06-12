#!/usr/bin/env python3
"""Fable audit proxy: local reverse proxy in front of api.anthropic.com.

Captures every request/response (and tool_use/tool_result blocks within them)
to an append-only, hash-chained, secret-redacted JSONL audit log.
Stdlib only. Python >= 3.8.
"""
import argparse
import gzip
import hashlib
import http.client
import http.server
import json
import os
import re
import socket
import socketserver
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

    def do_GET(self):
        if self.path == "/healthz":
            body = json.dumps({"ok": True, "audit_dir": str(AUDIT.dir)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def _proxy(self):
        if STRICT and not self._audit_writable():
            self.send_error(503, "audit log unwritable (FABLE_AUDIT_STRICT=1)")
            return

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
        usage = (resp_json or {}).get("usage")
        AUDIT.write("api_response", session_id=session_id, model=model,
                    http={"method": self.command, "path": self.path, "status": resp.status},
                    headers=redact_headers(dict(resp.getheaders())),
                    usage=usage, latency_ms=latency_ms, stream=is_stream,
                    response=resp_text)
        sse_text = resp_text if is_stream else None
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
    parser = argparse.ArgumentParser(description="Fable audit proxy")
    parser.add_argument("--port", type=int, default=int(os.environ.get("FABLE_PROXY_PORT", "8377")))
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()

    AUDIT.write("bootstrap_phase", phase="proxy_start",
                config={"port": args.port, "strict": STRICT,
                        "retention_days": RETENTION_DAYS, "audit_dir": str(AUDIT.dir)})
    threading.Thread(target=rotation_loop, daemon=True).start()
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"fable audit proxy listening on {args.bind}:{args.port} -> https://{UPSTREAM_HOST}")
    server.serve_forever()


if __name__ == "__main__":
    main()
