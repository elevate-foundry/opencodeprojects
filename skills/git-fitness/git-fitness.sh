#!/data/data/com.termux/files/usr/bin/bash
# git-fitness.sh — gated auto commit+push: only pushes if the diff passes a fitness function.
# Usage: git-fitness.sh [--repo <path>] [--dry-run] [--no-push] ["commit message"]
set -uo pipefail

REPO="$PWD"
DRY=0
PUSH=1
MSG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --no-push) PUSH=0; shift ;;
    *) MSG="$1"; shift ;;
  esac
done

MAX_DIFF_LINES="${GITFIT_MAX_DIFF_LINES:-2000}"
MAX_FILES="${GITFIT_MAX_FILES:-40}"
ALLOWED_BRANCHES="${GITFIT_BRANCHES:-main master}"

cd "$REPO" || { echo "FAIL: no such repo dir: $REPO"; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "FAIL: not a git repo: $REPO"; exit 1; }

branch=$(git rev-parse --abbrev-ref HEAD)
fails=0
say()  { echo "  [$1] $2"; }
fail() { say FAIL "$1"; fails=$((fails+1)); }
pass() { say ok "$1"; }

echo "git-fitness: $REPO @ $branch"

# ---- check 0: branch allowlist (never auto-push from feature/detached) ----
case " $ALLOWED_BRANCHES " in
  *" $branch "*) pass "branch '$branch' allowed" ;;
  *) fail "branch '$branch' not in allowlist ($ALLOWED_BRANCHES)" ;;
esac

# ---- collect changed files (staged + unstaged + untracked) ----
mapfile -t files < <(git status --porcelain | awk '{print $NF}' | sed 's/^"//;s/"$//')
[ ${#files[@]} -eq 0 ] && { echo "nothing to commit"; exit 0; }

# ---- check 1: file count + diff size sanity ----
[ ${#files[@]} -le "$MAX_FILES" ] \
  && pass "${#files[@]} files changed (cap $MAX_FILES)" \
  || fail "${#files[@]} files changed exceeds cap $MAX_FILES"
diff_lines=$( { git diff 2>/dev/null; git diff --cached 2>/dev/null; } | wc -l )
[ "$diff_lines" -le "$MAX_DIFF_LINES" ] \
  && pass "diff $diff_lines lines (cap $MAX_DIFF_LINES)" \
  || fail "diff $diff_lines lines exceeds cap $MAX_DIFF_LINES"

# ---- check 2: forbidden paths (credentials, env files, keys) ----
forbidden='(^|/)\.env($|\.|[^.])|(^|/)\.env$|id_rsa|id_ed25519|\.pem$|\.key$|\.gh_token|\.xmpp_pw|twilio\.env$|credentials|\.npmrc$|\.netrc$'
bad_paths=""
for f in "${files[@]}"; do
  echo "$f" | grep -qE "$forbidden" && bad_paths="$bad_paths $f"
done
[ -z "$bad_paths" ] && pass "no credential/env paths staged" || fail "forbidden paths:$bad_paths"

# ---- check 3: secret scan on added lines ----
secret_re='(api[_-]?key|secret|token|password|passwd)["'"'"']?\s*[:=]\s*["'"'"'][A-Za-z0-9_\-]{16,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|gho_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16}|xox[bp]-[A-Za-z0-9-]{20,}|AC[a-f0-9]{32}'
leaks=$( { git diff 2>/dev/null; git diff --cached 2>/dev/null; git ls-files --others --exclude-standard -z | xargs -0 -r cat 2>/dev/null; } \
  | grep -a -icE "$secret_re" 2>/dev/null || true )
[ "${leaks:-0}" -eq 0 ] && pass "no secret patterns in changes" || fail "$leaks possible secret(s) in changes"

# ---- check 4: syntax compile for changed source files ----
syn_fail=""
for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  case "$f" in
    *.py)  python3 -m py_compile "$f" 2>/dev/null || syn_fail="$syn_fail $f" ;;
    *.sh)  bash -n "$f" 2>/dev/null || syn_fail="$syn_fail $f" ;;
    *.json) python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f" 2>/dev/null || syn_fail="$syn_fail $f" ;;
    *.yaml|*.yml) python3 -c "import sys; [__import__('yaml').safe_load(open(sys.argv[1]))]" "$f" 2>/dev/null || true ;;
  esac
done
[ -z "$syn_fail" ] && pass "syntax OK for changed py/sh/json" || fail "syntax errors:$syn_fail"

# ---- check 5: skill manifest validation for changed skills ----
man_fail=""
for f in "${files[@]}"; do
  d=$(dirname "$f")
  case "$d" in
    skills/*)
      top="skills/$(echo "$d" | cut -d/ -f2)"
      m="$top/skill.yaml"
      if [ -d "$top" ]; then
        [ -f "$m" ] || { man_fail="$man_fail $top(no-manifest)"; continue; }
        for k in name version entrypoint; do
          grep -q "^$k:" "$m" || man_fail="$man_fail $top(missing:$k)"
        done
        e=$(grep '^entrypoint:' "$m" | cut -d: -f2 | tr -d ' ')
        [ -f "$top/$e" ] || man_fail="$man_fail $top(entrypoint-missing)"
      fi
      ;;
  esac
done
man_fail=$(echo "$man_fail" | tr ' ' '\n' | sort -u | tr '\n' ' ' | sed 's/^ *//;s/ *$//')
[ -z "$man_fail" ] && pass "skill manifests valid" || fail "manifest problems: $man_fail"

# ---- verdict ----
if [ "$fails" -gt 0 ]; then
  echo "VERDICT: UNFIT ($fails check(s) failed) — not committing, not pushing"
  exit 1
fi
echo "VERDICT: FIT"
[ "$DRY" -eq 1 ] && { echo "(dry-run: stopping before commit)"; exit 0; }

# ---- commit ----
[ -z "$MSG" ] && MSG="auto: $(git status --porcelain | awk '{print $NF}' | head -3 | tr '\n' ' ')($(date -u +%Y-%m-%dT%H:%MZ))"
GIT_ID=(-c user.name="${GITFIT_NAME:-salus-ryan}" -c user.email="${GITFIT_EMAIL:-ryan.barrett@salusfintech.com}")
git add -A
git "${GIT_ID[@]}" commit -m "$MSG" || { echo "FAIL: commit failed"; exit 1; }
echo "committed: $(git log --oneline -1)"

# ---- push (never force; current branch only) ----
[ "$PUSH" -eq 0 ] && { echo "(--no-push: done)"; exit 0; }
TOKEN_FILE="${GITFIT_TOKEN_FILE:-$HOME/.fable/.gh_token}"
if [ -f "$TOKEN_FILE" ]; then
  GH_TOKEN=$(cat "$TOKEN_FILE")
  git -c credential.helper="!f() { echo username=${GITFIT_NAME:-salus-ryan}; echo password=$GH_TOKEN; }; f" \
    push origin "$branch" || { echo "FAIL: push failed"; exit 1; }
else
  git push origin "$branch" || { echo "FAIL: push failed"; exit 1; }
fi
echo "pushed: origin/$branch"

# ---- post-push: auto-rebuild fable if opencode-src changed ----
if [ "${GITFIT_REBUILD:-1}" -eq 1 ] && [ -d "$REPO/opencode-src" ] \
  && printf '%s\n' "${files[@]}" | grep -q '^opencode-src/'; then
  echo "opencode-src changed — rebuilding fable"
  if (cd "$REPO/opencode-src" && go build -o "$HOME/.local/bin/fable.new" .); then
    mv "$HOME/.local/bin/fable.new" "$HOME/.local/bin/fable"
    echo "rebuilt+swapped ~/.local/bin/fable (running instances keep old inode; new code on next launch)"
  else
    echo "WARN: rebuild failed — binary unchanged"
  fi
fi
