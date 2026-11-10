# Changelog

## 1.1.1 — 2026-11-10

Fixes from a review of 1.1.0. Review modes, defaults, and the result contract are unchanged except where noted.

### Fixed

- Model output containing a lone surrogate no longer crashes terminal publication after a paid call. JSON artifacts are written with ASCII escapes through a uniquely named temporary file that is removed on failure, and encoding errors are handled like other artifact write failures.
- Git commands and the Codex child no longer inherit `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, or the related object and namespace variables. Started from a Git hook in a linked worktree, snapshot preparation previously staged files in the caller's real index. Read-only Git commands also run with `GIT_OPTIONAL_LOCKS=0`.
- Working-tree mode refuses a submodule that is only staged. The earlier check looked at the committed tree alone and silently omitted the submodule's content.
- A finding with an empty file and line 0 is accepted in committed and working-tree modes, as the prompt already requested for plan or objective findings. One such finding previously invalidated the whole review.
- A failed or timed-out `git worktree add` no longer leaves a locked worktree registered in the source repository. Cleanup always attempts a forced removal and retains the temporary root only when Git still lists the snapshot; a clean add failure now reports `error` rather than `cleanup_failed`.
- SIGHUP is handled like SIGINT and SIGTERM. A closed terminal previously killed the wrapper while Codex kept running with no terminal artifacts and a registered snapshot.

### Added

- `--git-timeout-seconds` (default 60, range 5 to 600) for repositories whose checkout exceeds the fixed limit.

### Validation

- 55 offline tests (54 run on macOS; one is Windows-only) pass on macOS with Python 3.11, and the suite also passes on Python 3.9. Each new regression test fails against the 1.1.0 runner. A no-model working-tree `--dry-run` passed against `codex-cli 0.163.0`. No real model run, Windows run, or Linux run was performed.

## 1.1.0 — 2026-10-14

Brings the process hardening and ergonomics of `claude-delegator` 8.x to this skill and adds code-grounded reviews. Collab mode and an executor helper are out of scope; the default model (Codex's built-in choice) and `medium` effort are unchanged.

### Added

- Code-grounded mode: `--repo PATH --head SHA` with an objective and no `--base`/`--working-tree` snapshots that exact commit with no diff and runs an objective-first prompt, so Codex can review a document or answer a question against the code read-only. It replaces the `git clone --local` plus untracked `REVIEW/` plus `--working-tree` workaround. Findings cite code locations, or an empty file and line 0 for the supplied document or question; the review `summary` carries the direct answer.
- `--prompt` for an inline objective, mutually exclusive with `--prompt-file`.
- Optional `--run-directory`. When omitted, the wrapper creates a durable temporary run directory. Every run prints `CODEX_DELEGATION_RUN_DIRECTORY=<path>` on stderr before preflight and includes `run_directory` and `mode` in the final JSON summary.

### Changed

- An existing empty run directory is accepted. Nonempty, symlinked, and in-repository run directories are refused, and a `.run-claim` file claims the directory exclusively.
- SIGINT/SIGTERM now publish a terminal `interrupted` status ("do not automatically retry") instead of a generic `error`. The entry point ignores repeated signals after the first, and final cleanup and artifact publication run with SIGINT/SIGTERM ignored.
- `codex` and `git` resolve only from absolute PATH entries, never Windows' implicit current-directory lookup. Windows `.cmd`/`.bat`/`.ps1` shims are still refused, and Windows process-tree cleanup uses `%SystemRoot%\System32\taskkill.exe`.
- Preflight (`codex exec --help`, `--version`, `login status`) and Git commands use file-backed capture with a timeout and process-group or process-tree kill instead of `subprocess.run`; preflight runs from a neutral temporary directory.
- The prompt reaches Codex from a temporary file instead of `communicate()` over a pipe, so a large prompt cannot block past the timeout on Windows.
- `--working-tree` rejects any explicit `--head`, matching the documented rule that it cannot combine with revision flags.

### Fixed

- A failed Windows `taskkill /T` is reported as uncertain cleanup even when the direct parent has already exited.
- POSIX cleanup no longer fails when the child's process group has already exited.

### Unchanged

- Read-only sandbox, `approval_policy=never`, suppressed user config, rules, project instructions, web search, hooks, plugins, apps, delegation and host skill discovery, no project code execution, the no-automatic-retry rule, and the `no_changes` path for committed and working-tree modes.

### Development

- The fake Codex child now also answers preflight calls. Nineteen new offline tests cover each change, including a real wrapper process that receives repeated SIGTERM. The suite has 46 tests: 45 passed on macOS with Python 3.11 on 2026-10-14 and one is Windows-only. No-model `--dry-run` checks against `codex-cli 0.154.0` also passed on macOS. Windows and Linux have not yet been validated for this release.

## 1.0.1 — 2026-09-16

- Pin Git patch prefixes so user diff formatting cannot break snapshot application.
- Resolve temporary roots before containment checks and reject rooted finding paths using both Windows and POSIX path semantics.
- Retry transient atomic-write locks, attempt all terminal artifacts after persistent failures, and emit recovery metadata without mislabeling a started run as preflight-only.
- Preserve timeout status and partial results when event output is truncated or malformed.
- Add regression coverage for all five confirmed review findings and related recovery cases.

## 1.0.0 — 2026-09-16

- Add Claude Code-to-Codex read-only review delegation for exact commit ranges, working-tree changes, and plans.
- Add model/effort selection, structured findings without count caps, native sandbox controls, and a configurable 30-minute process guard.
- Preserve atomic status/results, raw event logs, scope fingerprints, usage/debug metadata, and explicit no-blind-retry recovery.
- Add a shared Python standard-library runner and offline regression tests; no automatic installation, login, or publishing.
