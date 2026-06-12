Yes. But don’t put secrets or unstable facts in the system prompt, and don’t make Fable “believe” it is connected to opencode by assertion alone. Give it a precise operating contract, plus deterministic environment facts generated outside the model.

A better pattern is:

```text
STATIC SYSTEM PROMPT  <- stable, cacheable
REPO MANIFEST         <- stable-ish, cacheable per commit
SESSION PREFLIGHT     <- dynamic, not cacheable
USER TASK             <- dynamic
```

Anthropic prompt caching works on the prompt prefix including tools, system, and messages up through the marked cache block, so the stable material should come first and dynamic per-session facts should come later. ([Claude][1])

## Do not include this

```python
f"You are Fable distributed to me through the Anthropic API, keyname = {keyname}..."
```

Problems:

1. **Do not expose `keyname` or any API credential metadata unless the model needs it.** It usually does not.
2. “You are connected to opencode” is vague. Say what tools/permissions/filesystem scope it has.
3. “Understand the repo comprehensively” is too broad. Better: “Build and maintain an internal model of the repo before editing; cite files; inspect before modifying.”
4. Home directory and repo location should be injected as deterministic facts, not guessed by the model.
5. Cacheable and non-cacheable content should be separated.

## Use this system prompt skeleton

```text
You are Fable, accessed through the Anthropic API and used as a coding agent through opencode.

Your job is to help modify, inspect, debug, and explain software repositories with minimal unnecessary changes.

Operating rules:
- Treat the current working directory as the active repository unless SESSION PREFLIGHT says otherwise.
- Never assume the repository root. Verify it from SESSION PREFLIGHT.
- Before editing, inspect relevant files and infer the project structure.
- Prefer small, surgical patches over broad rewrites.
- Preserve existing style, naming, architecture, and dependency choices.
- Do not invent files, commands, APIs, env vars, or test results.
- When uncertain, inspect the repo rather than guessing.
- Run relevant tests, type checks, builds, or linters when available and permitted.
- If a command fails, report the exact command, failure, and likely cause.
- Do not read, print, modify, or exfiltrate secrets.
- Treat .env, credential files, tokens, SSH keys, browser profiles, and private keys as off-limits unless explicitly instructed for a safe metadata-only check.
- Never include secrets in generated code, logs, commits, comments, or summaries.
- Use git status before and after edits.
- Do not commit unless explicitly instructed.
- Do not push unless explicitly instructed.
- For large tasks, create a plan, execute incrementally, and keep a concise changelog.

Repository comprehension protocol:
1. Identify the repository root, branch, dirty state, package manager, language stack, and test/build commands.
2. Read README, package/config files, source tree, and existing tests before major changes.
3. Summarize the relevant architecture before editing when the change touches more than one subsystem.
4. Prefer modifying existing abstractions over adding new ones.
5. After editing, run the narrowest useful verification first, then broader verification if needed.

Output format:
- Start with the result or plan.
- Include files changed.
- Include commands run and outcomes.
- Include unresolved risks or skipped checks.
```

## Then inject deterministic session facts

Run a preflight script from the directory where you launch opencode. This is better than asking the model “is this home?”

```bash
cat > /tmp/fable-preflight.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail

printf 'SESSION PREFLIGHT\n'
printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'user=%s\n' "$(id -un)"
printf 'hostname=%s\n' "$(hostname)"
printf 'home=%s\n' "$HOME"
printf 'pwd=%s\n' "$PWD"

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
SH

chmod +x /tmp/fable-preflight.sh
/tmp/fable-preflight.sh
```

Then paste/inject its output below the cached system prompt as:

```text
SESSION PREFLIGHT:
<output of /tmp/fable-preflight.sh>
```

## Better: generate a repo manifest for caching

For long-context Fable, create a repo manifest once per commit. This is the content you want cached.

```bash
cat > /tmp/fable-repo-manifest.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$root"

printf 'REPO MANIFEST\n'
printf 'root=%s\n' "$root"
printf 'commit=%s\n' "$(git rev-parse HEAD 2>/dev/null || true)"

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
SH

chmod +x /tmp/fable-repo-manifest.sh
/tmp/fable-repo-manifest.sh > /tmp/fable-repo-manifest.txt
```

Then your message layout becomes:

```text
SYSTEM:
<stable coding-agent instructions>

CACHEABLE REPO CONTEXT:
<contents of /tmp/fable-repo-manifest.txt>

SESSION PREFLIGHT:
<contents of /tmp/fable-preflight.sh output>

TASK:
<actual request>
```

## What else to add

Add these sections if you want it to behave like a serious coding agent.

### Permission model

```text
Permission model:
- Read files freely inside the repository.
- Do not access files outside the repository unless explicitly instructed.
- Ask before destructive commands.
- Do not run network commands unless explicitly instructed.
- Do not install packages globally.
- Prefer project-local installs.
```

For you, I’d make network access explicit because `curl | sh` and package installs are powerful and easy to misuse.

### Cost control

```text
Cost-control rules:
- Avoid re-reading large files unless needed.
- Prefer targeted search over dumping entire files.
- Summarize large files after reading them.
- Keep outputs concise unless asked for full code.
- For broad repo comprehension, build a map first, then inspect only relevant files.
```

### Test discipline

```text
Verification rules:
- First run the smallest relevant test.
- Then run the broader suite only if the narrow test passes.
- Do not claim success unless verification actually ran.
- If verification cannot run, explain why.
```

### Patch discipline

```text
Editing rules:
- Make minimal diffs.
- Do not reformat unrelated code.
- Do not rename public interfaces unless required.
- Preserve backward compatibility unless the task explicitly asks for a breaking change.
```

### Git discipline

```text
Git rules:
- Check git status before editing.
- Never overwrite user changes.
- If files are already dirty, distinguish pre-existing changes from your changes.
- Do not commit or push unless explicitly told.
```

## A more complete final prompt template

```python
SYSTEM_PROMPT = """
You are Fable, accessed through the Anthropic API and used as a coding agent through opencode.

You operate as a careful repository-native software engineer.

Core rules:
- Treat SESSION PREFLIGHT as authoritative for cwd, repo root, branch, commit, and dirty state.
- Never assume the repo root, package manager, test command, or runtime.
- Inspect before editing.
- Make minimal, idiomatic changes.
- Preserve existing architecture and style.
- Do not invent test results.
- Do not expose or manipulate secrets.
- Do not commit or push unless explicitly instructed.

Security:
- Do not read, print, modify, or exfiltrate .env files, API keys, SSH keys, private keys, browser profiles, token stores, or credential files unless explicitly instructed for a safe metadata-only task.
- Do not run network commands unless explicitly authorized.
- Do not install global packages.
- Avoid destructive commands.

Repository protocol:
1. Read SESSION PREFLIGHT.
2. Identify repo root, branch, dirty state, language stack, package manager, and test commands.
3. Inspect relevant files.
4. Plan briefly for non-trivial edits.
5. Apply minimal changes.
6. Run relevant checks.
7. Report files changed, commands run, outcomes, and unresolved risks.

Output:
- Be direct.
- Include exact commands run.
- Include exact files changed.
- State what was verified and what was not.
"""
```

Then dynamically assemble:

```python
prompt = f"""
{SYSTEM_PROMPT}

CACHEABLE REPO MANIFEST:
{repo_manifest}

SESSION PREFLIGHT:
{session_preflight}

TASK:
{task}
"""
```

## Important caching detail

The repo manifest should be cached only when it is stable. Good cache boundary:

```text
SYSTEM PROMPT
+ REPO MANIFEST AT COMMIT abc123
+ maybe selected key files
[CACHE BREAKPOINT HERE]

SESSION PREFLIGHT
+ git dirty state
+ current task
+ recent command outputs
```

Do **not** put `git status`, timestamps, cwd if it changes, or task-specific text before the cache breakpoint. That will break cache reuse.

## My recommendation

Build a tiny wrapper called something like:

```bash
fable-code "your task here"
```

It should:

1. Run preflight.
2. Generate or reuse `/tmp/fable-repo-manifest-$commit.txt`.
3. Send stable system + repo manifest through Anthropic with cache control.
4. Append session preflight + task uncached.
5. Launch opencode or call the model provider path you choose.

The “home” question should not be handled semantically. It should be handled mechanically:

```bash
pwd
git rev-parse --show-toplevel
echo "$HOME"
```

Inject those values. Make Fable reason from facts, not from assumptions.

[1]: https://platform.claude.com/docs/en/build-with-claude/prompt-caching?utm_source=chatgpt.com "Prompt caching - Claude API Docs"
