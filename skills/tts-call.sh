#!/data/data/com.termux/files/usr/bin/bash
# tts-call.sh — Place a phone call and speak a message via TTS.
# Usage: tts-call.sh <phone_number> "<message>" [delay_seconds]
# Limitations (Samsung Galaxy S25, Termux Play Store build):
#  - CALL_PHONE permission unavailable, so the dialer opens and the USER must tap Call.
#  - TTS plays through the media stream; enable SPEAKERPHONE so the mic carries it into the call.
#  - One-way only: the agent cannot hear the callee. For interactive use, the user relays replies.
set -euo pipefail

NUMBER="${1:?usage: tts-call.sh <number> \"<message>\" [delay]}"
MESSAGE="${2:?missing message}"
DELAY="${3:-12}"

# Try direct call first (works if Termux:API F-Droid build w/ CALL_PHONE is installed)
if termux-telephony-call "$NUMBER" 2>/dev/null | grep -qv "not yet available"; then
  echo "Direct call placed to $NUMBER"
else
  am start -a android.intent.action.DIAL -d "tel:$NUMBER" >/dev/null 2>&1
  termux-tts-speak "Dialer is open. Please tap call and turn on speakerphone."
  echo "Dialer opened for $NUMBER. Waiting ${DELAY}s for user to connect + enable speaker..."
fi

sleep "$DELAY"
termux-tts-speak "$MESSAGE"
echo "Message spoken: $MESSAGE"
