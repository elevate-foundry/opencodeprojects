#!/data/data/com.termux/files/usr/bin/bash
# bio-gate.sh — human-presence gate for governed skill actions.
# Backends (in order): termux-fingerprint (BiometricPrompt), passphrase hash fallback.
# Usage: bio-gate.sh ["reason"] | bio-gate.sh --enroll
# Exit 0 = approved, 1 = denied/unavailable.
set -uo pipefail

SECRET_FILE="$HOME/.fable/.gate_secret"
REASON="${1:-confirm action}"

hashpw() { printf '%s' "$1" | sha256sum | cut -d' ' -f1; }

if [ "$REASON" = "--enroll" ]; then
  printf "bio-gate enroll — choose a gate passphrase: " >&2
  read -rs pw; echo >&2
  printf "repeat: " >&2
  read -rs pw2; echo >&2
  [ "$pw" = "$pw2" ] || { echo "mismatch"; exit 1; }
  [ ${#pw} -ge 6 ] || { echo "too short (min 6)"; exit 1; }
  hashpw "$pw" > "$SECRET_FILE" && chmod 600 "$SECRET_FILE"
  echo "enrolled -> $SECRET_FILE"
  exit 0
fi

# Backend 1: real biometric via Termux:API (when available)
if command -v termux-fingerprint >/dev/null 2>&1; then
  out=$(termux-fingerprint -t "Fable" -d "$REASON" 2>&1 || true)
  if echo "$out" | grep -q AUTH_RESULT_SUCCESS; then
    echo "[bio-gate] biometric OK"
    exit 0
  elif echo "$out" | grep -q AUTH_RESULT; then
    echo "[bio-gate] biometric DENIED"
    exit 1
  fi
  # fall through: termux-fingerprint present but non-functional (Play Store build)
fi

# Backend 2: passphrase hash
[ -f "$SECRET_FILE" ] || { echo "[bio-gate] no backend: run 'bio-gate.sh --enroll' first"; exit 1; }
printf "[bio-gate] %s — passphrase: " "$REASON" >&2
read -rs pw; echo >&2
if [ "$(hashpw "$pw")" = "$(cat "$SECRET_FILE")" ]; then
  echo "[bio-gate] passphrase OK"
  exit 0
fi
echo "[bio-gate] DENIED"
exit 1
