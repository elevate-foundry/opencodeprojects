#!/usr/bin/env bash
# Session preflight: deterministic environment facts injected below the cached prompt.
set -euo pipefail

printf 'SESSION PREFLIGHT\n'
printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'user=%s\n' "$(id -un)"
printf 'hostname=%s\n' "$(hostname)"
printf 'home=%s\n' "$HOME"
printf 'pwd=%s\n' "$PWD"

# form factor (mobile/laptop/desktop) for audit context
form_factor="desktop"
if [ -n "${TERMUX_VERSION:-}" ]; then
  form_factor="mobile"
elif [ -d /sys/class/power_supply ] && ls /sys/class/power_supply 2>/dev/null | grep -qi '^bat'; then
  form_factor="laptop"
fi
printf 'form_factor=%s\n' "$form_factor"

if git rev-parse --show-toplevel >/dev/null 2>&1; then
  printf 'git_root=%s\n' "$(git rev-parse --show-toplevel)"
  printf 'git_branch=%s\n' "$(git branch --show-current 2>/dev/null || true)"
  printf 'git_commit=%s\n' "$(git rev-parse HEAD)"
  printf 'git_dirty='
  if [ -n "$(git status --porcelain)" ]; then
    printf 'true\n'
  else
    printf 'false\n'
  fi
  printf 'git_status_porcelain<<EOF\n'
  git status --porcelain
  printf 'EOF\n'
else
  printf 'git_root=\n'
  printf 'git_branch=\n'
  printf 'git_commit=\n'
  printf 'git_dirty=unknown_not_git_repo\n'
fi

printf 'top_level_files<<EOF\n'
find . -maxdepth 2 \
  -not -path './.git/*' \
  -not -path './node_modules/*' \
  -not -path './.venv/*' \
  -not -path './venv/*' \
  -not -path './dist/*' \
  -not -path './build/*' \
  -print | sort | sed 's#^\./##' | head -300
printf 'EOF\n'

printf 'detected_manifests<<EOF\n'
find . -maxdepth 3 \( \
  -name package.json -o \
  -name pyproject.toml -o \
  -name requirements.txt -o \
  -name uv.lock -o \
  -name poetry.lock -o \
  -name Cargo.toml -o \
  -name go.mod -o \
  -name Makefile -o \
  -name justfile -o \
  -name docker-compose.yml -o \
  -name Dockerfile -o \
  -name tsconfig.json -o \
  -name vite.config.ts \
\) -not -path './node_modules/*' -not -path './.git/*' | sort
printf 'EOF\n'
