# Migration: Claude Fable 5 → Opus / Sonnet (2026-06-12)

## Why this migration happened

This project was originally built around **Claude Fable 5** (`claude-fable-5`) as the
primary coding model. On **Friday, June 12, 2026**, the US government issued an
**export control directive** ordering Anthropic to suspend all access to Fable 5
(and its sibling, Mythos 5) for **all users**, citing a potential jailbreak /
national-security concern.

As a result, the `claude-fable-5` API model began returning **HTTP 404**, which
broke the system end-to-end:

- `bootstrap.sh` smoke test failed.
- The `fable` TUI launched but could not respond (`failed to process events`).
- The agent defaulted to a model that no longer exists.

## What changed

To keep the system functional while Fable 5 is suspended, the model defaults were
repointed to currently-available models:

| Role | Was | Now |
|------|-----|-----|
| Coder agent | `claude-fable-5` | `claude-opus-4` |
| Summarizer / task | `claude-fable-5` | `claude-sonnet-4` |
| Title | `claude-4-sonnet` | `claude-3.5-haiku` |
| Ghost text (predictive) | `claude-haiku-4-5` | `claude-haiku-4-5` (unchanged) |

Files touched:

- `opencode-src/internal/config/config.go` — Anthropic agent defaults.
- `opencode-src/internal/llm/models/anthropic.go` — the `ClaudeFable5` entry now
  aliases the real `claude-sonnet-4-5-20250929` API model instead of the
  offline `claude-fable-5`, so any lingering reference degrades gracefully
  rather than 404-ing.
- `bootstrap.sh`, `opencode.json`, `bin/fable-cli`, prompts — removed
  `claude-fable-5` references.

## Sources

- Anthropic official statement — <https://www.anthropic.com/news/fable-mythos-access>
- WIRED — <https://www.wired.com/story/anthropic-says-us-government-ordered-it-to-shut-down-mythos-models/>
- NYT — <https://www.nytimes.com/2026/06/12/technology/anthropic-mythos-fable5-blocked.html>
- NBC News — <https://www.nbcnews.com/tech/tech-news/anthropic-suspends-new-ai-models-fable-mythos-government-directive-rcna349901>

## Restoring Fable 5

Anthropic stated it believes the directive is a misunderstanding and is "working to
restore access as soon as possible." If/when `claude-fable-5` is reinstated, the
coder default can be repointed by reverting the `config.go` change (or setting
`FABLE_MODEL=claude-fable-5`).
