#!/data/data/com.termux/files/usr/bin/bash
# twilio-sms.sh — Send SMS via Twilio API (true two-way capable).
# Usage: twilio-sms.sh <to_number> "<message>"
# Requires in ~/.fable/twilio.env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
set -euo pipefail

ENV_FILE="$HOME/.fable/twilio.env"
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE — add Twilio credentials first."; exit 1; }
source "$ENV_FILE"

TO="${1:?usage: twilio-sms.sh <to_number> \"<message>\"}"
MSG="${2:?missing message}"

python3 - "$TO" "$MSG" <<'PY'
import os, sys, urllib.request, urllib.parse, base64, json
sid, tok, frm = os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"], os.environ["TWILIO_FROM_NUMBER"]
to, msg = sys.argv[1], sys.argv[2]
if not to.startswith("+"): to = "+1" + to
data = urllib.parse.urlencode({"To": to, "From": frm, "Body": msg}).encode()
req = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=data)
req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{tok}".encode()).decode())
r = json.load(urllib.request.urlopen(req))
print(f"sent sid={r['sid']} status={r['status']}")
PY
