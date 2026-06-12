#!/usr/bin/env bash
# Fable: single-command Termux installer.
#
# Paste this into Termux:
#   curl -fsSL https://raw.githubusercontent.com/salus-ryan/opencodeprojects/main/scripts/termux-install.sh | bash
#
# Or if you prefer not to pipe to bash:
#   curl -fsSL -o fable-install.sh https://raw.githubusercontent.com/salus-ryan/opencodeprojects/main/scripts/termux-install.sh
#   bash fable-install.sh
#
# What it does:
#   1. Installs Termux packages: python, curl, git, golang (for building opencode)
#   2. Clones the repo (or pulls if already present)
#   3. Runs bootstrap.sh — which auto-opens a browser page for your API key if needed
#   4. Launches Fable
set -euo pipefail

REPO_URL="${FABLE_REPO_URL:-https://github.com/salus-ryan/opencodeprojects.git}"
INSTALL_DIR="${FABLE_INSTALL_DIR:-$HOME/opencodeprojects}"

echo "=== Fable Termux Installer ==="

# Step 1: Install Termux packages
echo "[1/3] Installing packages..."
pkg update -y
pkg install -y python curl git golang

# Step 2: Clone or update repo
echo "[2/3] Getting Fable..."
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "  repo exists at $INSTALL_DIR — pulling latest"
  git -C "$INSTALL_DIR" pull --ff-only origin main 2>/dev/null || true
else
  echo "  cloning $REPO_URL"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Step 3: Bootstrap (handles everything else including key prompt)
echo "[3/3] Running bootstrap..."
echo ""
echo "  If you haven't set an API key yet, a browser page will open"
echo "  for you to paste your Anthropic key. Just paste it and tap Save."
echo ""
cd "$INSTALL_DIR" && bash bootstrap.sh
