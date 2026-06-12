#!/usr/bin/env bash
# Assemble the dynamic Fable system prompt from layered sources.
# Output: prompts/system.md (overwritten each run)
#
# Layers (top = most stable / cacheable, bottom = most dynamic):
#   1. prompts/core.md          — static operating contract
#   2. repo manifest            — per-commit, cached at ~/.fable/cache/manifest-<commit>.txt
#   3. ~/.fable/memory.md       — learned patterns, grows across sessions
#   4. session preflight        — per-invocation environment facts
#   5. ~/.fable/sessions/recent.md — recent session summaries
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FABLE_HOME="${FABLE_HOME:-$HOME/.fable}"
OUTPUT="$REPO_ROOT/prompts/system.md"

mkdir -p "$FABLE_HOME/sessions" "$FABLE_HOME/cache"

# ---------- 1. static core ----------
core="$REPO_ROOT/prompts/core.md"
if [ ! -f "$core" ]; then
  echo "ERROR: $core not found" >&2; exit 1
fi

# ---------- 2. repo manifest (generate or reuse) ----------
manifest=""
if git -C "$REPO_ROOT" rev-parse HEAD >/dev/null 2>&1; then
  commit="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  cache_file="$FABLE_HOME/cache/manifest-$commit.txt"
  if [ -f "$cache_file" ]; then
    manifest="$cache_file"
  elif [ -x "$REPO_ROOT/scripts/repo-manifest.sh" ]; then
    (cd "$REPO_ROOT" && bash "$REPO_ROOT/scripts/repo-manifest.sh" > "$cache_file" 2>/dev/null) || true
    [ -s "$cache_file" ] && manifest="$cache_file"
  fi
fi

# ---------- 3. memory ----------
memory="$FABLE_HOME/memory.md"
[ -f "$memory" ] || touch "$memory"

# ---------- 4. session preflight ----------
preflight=""
if [ -x "$REPO_ROOT/scripts/preflight.sh" ]; then
  preflight="$(cd "$REPO_ROOT" && bash "$REPO_ROOT/scripts/preflight.sh" 2>/dev/null)" || true
fi

# ---------- 5. session history ----------
history="$FABLE_HOME/sessions/recent.md"
# Build recent.md from the last 10 session summaries
if ls "$FABLE_HOME/sessions"/session-*.md >/dev/null 2>&1; then
  tail -q -n 100 "$(ls -t "$FABLE_HOME/sessions"/session-*.md | head -10 | tac)" > "$history" 2>/dev/null || true
fi
[ -f "$history" ] || touch "$history"

# ---------- assemble ----------
{
  printf '<!-- AUTO-ASSEMBLED by scripts/assemble-prompt.sh at %s -->\n\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  printf '# STATIC CORE\n\n'
  cat "$core"
  printf '\n\n'

  if [ -n "$manifest" ] && [ -s "$manifest" ]; then
    printf '# REPO MANIFEST (cached per commit)\n\n'
    printf '```\n'
    cat "$manifest"
    printf '\n```\n\n'
  fi

  if [ -s "$memory" ]; then
    printf '# LEARNED PATTERNS\n\n'
    printf 'These are patterns, preferences, and knowledge accumulated across previous sessions.\n'
    printf 'Use them. Do not re-ask questions answered here.\n\n'
    cat "$memory"
    printf '\n\n'
  else
    printf '# LEARNED PATTERNS\n\n'
    printf 'No learned patterns yet. As you work, append useful discoveries to ~/.fable/memory.md.\n\n'
  fi

  if [ -n "$preflight" ]; then
    printf '# SESSION PREFLIGHT\n\n'
    printf '```\n%s\n```\n\n' "$preflight"
  fi

  if [ -s "$history" ]; then
    printf '# SESSION HISTORY (recent sessions)\n\n'
    cat "$history"
    printf '\n'
  else
    printf '# SESSION HISTORY\n\nNo previous sessions recorded yet.\n'
  fi

} > "$OUTPUT"

wc -l < "$OUTPUT" | xargs -I{} printf 'assembled %s ({} lines) from: core' "$OUTPUT"
[ -n "$manifest" ] && printf ' + manifest'
[ -s "$memory" ] && printf ' + memory'
[ -n "$preflight" ] && printf ' + preflight'
[ -s "$history" ] && printf ' + history'
printf '\n'
