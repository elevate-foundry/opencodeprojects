#!/usr/bin/env python3
"""send-email.py - send email via SMTP using credentials from ~/.fable/smtp.env

Usage: send-email.py <to> <subject> <body>
       echo "body" | send-email.py <to> <subject> -

smtp.env keys: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM (optional, defaults to SMTP_USER)
"""
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

ENV_FILE = os.path.expanduser("~/.fable/smtp.env")
MAX_BODY = int(os.environ.get("EMAIL_MAX_BODY_CHARS", "10000"))


def load_env(path):
    if not os.path.exists(path):
        sys.exit(f"missing {path} — copy smtp.env.example and fill in credentials")
    cfg = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    for req in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS"):
        if req not in cfg:
            sys.exit(f"smtp.env missing {req}")
    return cfg


def main():
    if len(sys.argv) != 4:
        sys.exit("usage: send-email.py <to> <subject> <body|->")
    to, subject, body = sys.argv[1], sys.argv[2], sys.argv[3]
    if body == "-":
        body = sys.stdin.read()
    if len(body) > MAX_BODY:
        sys.exit(f"body exceeds {MAX_BODY} chars — refusing")
    if "@" not in to or " " in to:
        sys.exit(f"invalid recipient: {to}")

    cfg = load_env(ENV_FILE)
    msg = EmailMessage()
    msg["From"] = cfg.get("SMTP_FROM", cfg["SMTP_USER"])
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    port = int(cfg["SMTP_PORT"])
    ctx = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(cfg["SMTP_HOST"], port, context=ctx, timeout=30)
    else:
        server = smtplib.SMTP(cfg["SMTP_HOST"], port, timeout=30)
        server.starttls(context=ctx)
    try:
        server.login(cfg["SMTP_USER"], cfg["SMTP_PASS"])
        server.send_message(msg)
    finally:
        server.quit()
    print(f"sent: to={to} subject={subject!r} ({len(body)} chars)")


if __name__ == "__main__":
    main()
