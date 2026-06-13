#!/usr/bin/env bash
# fable-cli single-command installer (Termux / Linux / macOS).
#
# Run:
#   curl -fsSL https://raw.githubusercontent.com/elevate-foundry/opencodeprojects/main/scripts/cli-install.sh | bash
#
# What it does:
#   1. Installs python + git (Termux: pkg; macOS: assumes brew/python3 present)
#   2. Clones or updates the repo
#   3. Ensures ~/opencodeprojects/.env has ANTHROPIC_API_KEY (prompts if missing)
#   4. Symlinks `fable` -> bin/fable-cli on PATH
#   5. Runs the smoke test
#
# No Go build, no audit proxy, no opencode binary. Pure Python stdlib.
set -euo pipefail

REPO_URL="${FABLE_REPO_URL:-https://github.com/elevate-foundry/opencodeprojects.git}"
INSTALL_DIR="${FABLE_INSTALL_DIR:-$HOME/opencodeprojects}"
BIN_DIR="$HOME/.local/bin"

echo "=== fable-cli installer ==="

# Step 1: dependencies
echo "[1/5] Installing dependencies (python, git)..."
if command -v pkg >/dev/null 2>&1; then
  pkg install -y python git >/dev/null 2>&1 || pkg install -y python git
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y && sudo apt-get install -y python3 git
elif command -v brew >/dev/null 2>&1; then
  command -v python3 >/dev/null 2>&1 || brew install python
  command -v git >/dev/null 2>&1 || brew install git
fi

# Resolve python
PYTHON="$(command -v python3 || command -v python)"
[ -n "$PYTHON" ] || { echo "ERROR: python not found" >&2; exit 1; }

# Step 2: clone or update
echo "[2/5] Getting the repo..."
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "  updating $INSTALL_DIR from $REPO_URL"
  # Fetch directly from REPO_URL (don't trust existing 'origin', which may
  # track an upstream that lacks fable-cli) and hard-reset the working tree
  # to match it exactly. This is an installer; local edits to tracked files
  # are intentionally discarded. (.env and opencode.json are gitignored and
  # therefore preserved.)
  git -C "$INSTALL_DIR" fetch "$REPO_URL" main
  git -C "$INSTALL_DIR" reset --hard FETCH_HEAD
else
  echo "  cloning into $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Sanity: confirm fable-cli actually exists after sync
if [ ! -f "$INSTALL_DIR/bin/fable-cli" ]; then
  echo "ERROR: bin/fable-cli missing after sync — repo may be wrong." >&2
  echo "  Try: rm -rf $INSTALL_DIR  and re-run this installer." >&2
  exit 1
fi

# Step 3: ensure .env has a key
echo "[3/5] Checking API key..."
ENV_FILE="$INSTALL_DIR/.env"
need_key=1
if [ -f "$ENV_FILE" ] && grep -q '^ANTHROPIC_API_KEY=' "$ENV_FILE"; then
  val="$(grep '^ANTHROPIC_API_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
  [ -n "$val" ] && need_key=0
fi
if [ "$need_key" -eq 1 ]; then
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" > "$ENV_FILE"
    echo "  wrote key from environment"
  else
    printf "  Paste your Anthropic API key (sk-ant-...): "
    read -r key </dev/tty
    echo "ANTHROPIC_API_KEY=$key" > "$ENV_FILE"
  fi
  chmod 600 "$ENV_FILE"
fi

# Step 4: symlink fable on PATH
echo "[4/5] Linking 'fable' command..."
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/bin/fable-cli" "$BIN_DIR/fable"
chmod +x "$INSTALL_DIR/bin/fable-cli"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo "  adding $BIN_DIR to PATH in shell rc"
    rc="$HOME/.bashrc"; [ -n "${ZSH_VERSION:-}" ] && rc="$HOME/.zshrc"
    echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$rc"
    export PATH="$BIN_DIR:$PATH"
    ;;
esac

# Step 5: smoke test
echo "[5/5] Running smoke test..."
set -a; . "$ENV_FILE"; set +a
unset ANTHROPIC_BASE_URL 2>/dev/null || true
if "$PYTHON" "$INSTALL_DIR/bin/fable-cli" --smoke-test; then
  echo ""
  echo "✓ Done. Start the agent with:  fable"
  echo "  (or: python3 $INSTALL_DIR/bin/fable-cli)"
else
  echo ""
  echo "✗ Smoke test failed — check the output above." >&2
  exit 1
fi
