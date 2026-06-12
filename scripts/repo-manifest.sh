#!/usr/bin/env bash
# Per-commit cacheable repo manifest. Output is stable for a given commit,
# making it safe to place before the Anthropic prompt-cache breakpoint.
# Cached at: ~/.fable/cache/manifest-<commit>.txt
set -euo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$root"
commit="$(git rev-parse HEAD 2>/dev/null || echo nogit)"

cache_dir="${FABLE_HOME:-$HOME/.fable}/cache"
cache_file="$cache_dir/manifest-$commit.txt"
if [ "$commit" != "nogit" ] && [ -f "$cache_file" ]; then
  cat "$cache_file"
  exit 0
fi

generate() {
  printf 'REPO MANIFEST\n'
  printf 'root=%s\n' "$root"
  printf 'commit=%s\n' "$commit"

  printf '\nFILES\n'
  git ls-files 2>/dev/null | sed \
    -e '/^node_modules\//d' \
    -e '/^dist\//d' \
    -e '/^build\//d' \
    -e '/^\.venv\//d' \
    -e '/^venv\//d' \
    -e '/^\.git\//d' \
    | sort

  printf '\nKEY FILE CONTENTS\n'
  for f in \
    README.md \
    package.json \
    pyproject.toml \
    requirements.txt \
    Makefile \
    justfile \
    docker-compose.yml \
    tsconfig.json \
    vite.config.ts \
    src/index.ts \
    src/main.ts \
    src/index.py \
    main.py
  do
    if [ -f "$f" ]; then
      printf '\n--- FILE: %s ---\n' "$f"
      sed -n '1,240p' "$f"
    fi
  done
}

if [ "$commit" != "nogit" ]; then
  mkdir -p "$cache_dir"
  generate > "$cache_file"
  cat "$cache_file"
else
  generate
fi
