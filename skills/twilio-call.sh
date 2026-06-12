#!/data/data/com.termux/files/usr/bin/bash
# twilio-call.sh — Place an outbound call that speaks a TTS message (Twilio <Say>).
# Usage: twilio-call.sh <to_number> "<message>"
# Requires in ~/.fable/twilio.env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
set -euo pipefail

ENV_FILE="$HOME/.fable/twilio.env"
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE — add Twilio credentials first."; exit 1; }
source "$ENV_FILE"

TO="${1:?usage: twilio-call.sh <to_number> \"<message>\"}"
MSG="${2:?missing message}"

python3 - "$TO" "$MSG" <<'PY'
import os, sys, urllib.request, urllib.parse, base64, json
from xml.sax.saxutils import escape
sid, tok, frm = os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"], os.environ["TWILIO_FROM_NUMBER"]
to, msg = sys.argv[1], sys.argv[2]
if not to.startswith("+"): to = "+1" + to
twiml = f'<Response><Say voice="Polly.Joanna">{escape(msg)}</Say></Response>'
data = urllib.parse.urlencode({"To": to, "From": frm, "Twiml": twiml}).encode()
req = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json", data=data)
req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{tok}".encode()).decode())
r = json.load(urllib.request.urlopen(req))
print(f"call sid={r['sid']} status={r['status']}")
PY
