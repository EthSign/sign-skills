# Changelog

Notable changes to Claude Delegator, newest first. Dates reflect repository
commit dates. Versions refer to wrapper versions; platform-specific changes
are identified below. This history begins with the first published commit.

## 7.2.1 — 2026-09-08

Windows fixes; the macOS wrapper remains at 7.2.0.

- Terminate surviving Claude child processes when stream setup or process I/O fails.
- Reject malformed JSON stream lines as incomplete reviews while preserving recovered evidence.
- Publish terminal status, result, and metadata files for preflight failures after run-directory initialization, retaining both start flags as false.
- Add regression coverage for all three failure paths, verified on PowerShell 7 and Windows PowerShell 5.1.

## 7.2.0 — 2026-09-08

- Change the default model from the moving `opus` alias to `fable` on Windows and macOS; retain `high` effort.
- Document per-run model selection through `-Model` on Windows and `--model` on macOS, supporting aliases and full model IDs.
- Integrate the newer macOS implementation and reliability improvements into the installed distribution.

## Documentation — 2026-09-03

- Add a project README covering platform support, installation, usage, diagnostics, and tests.

## 7.1.23 — 2026-09-02

- Add a native macOS entrypoint compatible with system Bash 3.2, without requiring PowerShell, Homebrew, jq, or Python.
- Add macOS regression tests and platform-specific invocation instructions.
- Improve Windows handling of changed submodule pointers, dirty submodules, path resolution, and isolated bounded-analysis working directories.
- Tighten review completion checks for authentication failures, invalid or absent model usage, final completion markers, snapshot cleanup, and durable-result publication.

## 7.1.0 — 2026-09-01

- Add `-RunDirectory` for durable status, streamed output, results, and metadata.
- Record run IDs, prompt hashes, process IDs, timestamps, and start-attempt flags for recovery.
- Spool stdout and stderr during execution and atomically publish terminal JSON artifacts.
- Require callers to preserve and poll long-running shell session IDs, and inspect durable artifacts before considering a retry.
- Add Windows durability regression tests.

## 7.0.0 — 2026-08-31

- First published skill, using the installed Claude Code CLI for read-only analysis and code reviews.
- Review verified commit ranges or frozen working-tree changes in temporary detached worktrees.
- Use Claude Code's native `/code-review` workflow for repository reviews and a completion-marker protocol for bounded analysis.
- Default to Opus/high with subscription-aware budget handling, diagnostic metadata, a wall-clock timeout, and no automatic retry after Claude starts.
- Restrict repository review tools to `Read`, `Glob`, and `Grep`; disable tools for bounded analysis.
