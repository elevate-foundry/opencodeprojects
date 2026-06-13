#!/data/data/com.termux/files/usr/bin/bash
# local-llm.sh — query the on-device speculative-decoding llama-server.
# Usage: local-llm.sh "<prompt>" [max_tokens]
#        local-llm.sh --start | --stop | --status
set -euo pipefail
PORT="${LOCAL_LLM_PORT:-8378}"
MODELS="$HOME/models"
TARGET="${LOCAL_LLM_TARGET:-$MODELS/SmolLM2-1.7B-Instruct-Q4_K_M.gguf}"
DRAFT="${LOCAL_LLM_DRAFT:-$MODELS/SmolLM2-360M-Instruct-Q4_K_M.gguf}"
LOG="$HOME/.fable/llama-server.log"

case "${1:?usage: local-llm.sh \"<prompt>\" | --start | --stop | --status}" in
  --start)
    pgrep -f "llama-server.*$PORT" >/dev/null && { echo "already running"; exit 0; }
    nohup llama-server -m "$TARGET" -md "$DRAFT" --port "$PORT" -t 4 >"$LOG" 2>&1 &
    for _ in $(seq 1 30); do
      sleep 2
      curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && { echo "started (spec-decode: $(basename "$DRAFT") drafting for $(basename "$TARGET"))"; exit 0; } || true
      python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:$PORT/health',timeout=2)" 2>/dev/null && { echo "started"; exit 0; }
    done
    echo "failed to start; see $LOG"; exit 1 ;;
  --stop)
    pkill -f "llama-server.*$PORT" && echo stopped || echo "not running" ;;
  --status)
    pgrep -f "llama-server.*$PORT" >/dev/null && echo running || echo stopped ;;
  *)
    prompt="$1"; max="${2:-${LOCAL_LLM_MAX_TOKENS:-300}}"
    python3 - "$prompt" "$max" "$PORT" <<'EOF'
import json, sys, time, urllib.request
prompt, max_tokens, port = sys.argv[1], int(sys.argv[2]), sys.argv[3]
body = json.dumps({"messages": [{"role": "user", "content": prompt}],
                   "max_tokens": max_tokens, "temperature": 0.3}).encode()
t = time.time()
req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                             data=body, headers={"content-type": "application/json"})
r = json.loads(urllib.request.urlopen(req, timeout=600).read())
dt = time.time() - t
print(r["choices"][0]["message"]["content"])
u = r.get("usage", {})
print(f"[local-llm] {u.get('completion_tokens',0)} tok in {dt:.1f}s "
      f"({u.get('completion_tokens',0)/dt:.1f} tok/s) cost=$0", file=sys.stderr)
EOF
    ;;
esac
