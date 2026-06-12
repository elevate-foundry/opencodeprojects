#!/data/data/com.termux/files/usr/bin/bash
# send-text.sh — Send an SMS to a phone number.
# Usage: send-text.sh <phone_number> "<message>"
# Limitations (Samsung Galaxy S25, Termux Play Store build):
#  - termux-sms-send unavailable (Termux:API not on Play Store), so this opens
#    the messaging app with the text pre-filled; the USER must tap Send.
set -euo pipefail

NUMBER="${1:?usage: send-text.sh <number> \"<message>\"}"
MESSAGE="${2:?missing message}"

# Try direct send first (works if Termux:API F-Droid build is installed)
if termux-sms-send -n "$NUMBER" "$MESSAGE" 2>/dev/null | grep -qv "not yet available"; then
  echo "SMS sent directly to $NUMBER"
else
  am start -a android.intent.action.SENDTO -d "sms:$NUMBER" --es sms_body "$MESSAGE" >/dev/null 2>&1
  echo "Messaging app opened for $NUMBER with text pre-filled. User must tap Send."
fi
