# Fable.md — Agent Guide

## Build / Test / Lint (main code in opencode-src/, Go 1.24)
- Build: `cd opencode-src && go build ./...`
- Test all: `cd opencode-src && go test ./...`
- Single test: `cd opencode-src && go test ./internal/llm/prompt/ -run TestGetContextFromPaths -v`
- Format: `gofmt -w .` (always run before finishing); Vet: `go vet ./...`
- Scripts: `bash scripts/preflight.sh`, `bash scripts/assemble-prompt.sh` (regenerates prompts/system.md)

## Code Style (Go)
- Imports: stdlib first, then third-party, then `github.com/opencode-ai/opencode/internal/...`; grouped with blank lines (goimports order).
- Naming: exported CamelCase with tool-name consts like `GlobToolName`; params structs as `XxxParams` with `json:"snake_case"` tags.
- Errors: return wrapped errors via `fmt.Errorf("...: %w", err)`; log via `internal/logging`; no panics in library code.
- Tools live in `internal/llm/tools/`, one file per tool, with a long const description string and `XxxParams` struct.
- Tests: standard `testing` package, table-driven where sensible, `_test.go` next to source.
- No comments unless logic is non-obvious; keep diffs minimal and idiomatic.

## Project Rules
- Never read/print `.env` or secrets; never commit/push unless explicitly asked.
- prompts/system.md is auto-generated — edit prompts/core.md and re-run assemble-prompt.sh instead.
