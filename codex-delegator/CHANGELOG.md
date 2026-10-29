# Changelog

## 1.2.0 — 2026-10-28

- Add explicit `--mode task` for Claude Code to delegate implementation and testing to Codex in a retained detached worktree, starting from `--head` or `HEAD`. Review remains the default; its modes and result contract are preserved.
- Task mode uses a restricted native permission profile, enables applicable project instructions, accepts file-change events, and validates a task result with changed files, test outcomes, and limitations.
- Preserve task worktrees on success and failure. Capture actual tracked diffs and nonignored new files separately from model-reported changes, with hashes and recovery metadata. Evidence collection errors invalidate completion without deleting partial work.
- Stop the Windows task job or original POSIX process group before final log parsing and evidence capture, including after successful parent exit. Windows starts suspended until job assignment succeeds. Keep review process handling unchanged.
- Add task selection, source-preservation, binary-file, failure, interruption, artifact recovery, and schema regression tests. Decode fixture stdin as UTF-8 consistently on Windows.
- Validate offline behavior and no-model dry runs on Windows using Python 3.12 and `codex-cli 0.165.0-alpha.1.2`. The initial real task smoke run was blocked because ignoring user config dropped the Windows sandbox backend; it correctly reported incomplete. See the Windows fix below. Model-driven edits/project tests and native macOS/Linux runs remain unverified.

### Review fixes — 2026-10-29

- Preserve interrupted, timeout, and other primary task failures when evidence collection, cleanup, or artifact publication also fails. Retain secondary diagnostics separately.
- Distinguish Windows launch failures from cleanup failures and keep failed job termination checks unconfirmed on subsequent cleanup calls.
- Tolerate disappearing Linux process/thread entries while preserving fail-closed handling of unreadable entries.
- Limit task writes to its worktree and retained scratch directory through a fresh permission profile, with model-free checks rejecting legacy selection or managed fallback. Set `TEMP`, `TMP`, and `TMPDIR` to scratch. Refuse pre-existing task evidence output paths instead of following them.
- Add regression tests for the reproduced recovery failures, scratch configuration/environment, Linux disappearance/permission errors, and evidence destination collisions.
- Validate the final Windows suite: 66 tests, 64 passed and 2 platform skips. The installed CLI passed both no-model permission checks and the task dry run; live task execution remains unverified.

### Windows execution fix — 2026-10-29

- Explicitly select MXC for native Windows task mode. `--ignore-user-config` had removed the configured backend; with approvals disabled, Codex rejected all commands, including file reads.
- Before any model call, exercise real schema reads, worktree/scratch writes, and artifact write denial through the native sandbox under a Windows Job Object. Isolated Python runs only the wrapper's probe. Record `task_execution_verified`; refuse unavailable or unenforceable sandbox configurations without a fallback.
- Validate the native wrapper dry run on this Windows host: both permission selection and actual sandbox execution passed without a model call. Model-driven implementation and project tests remain pending.
- Verify PowerShell file reads and `git status` under the corrected profile and Job Object. The Windows offline suite passed 66 tests with 2 platform skips (68 total).

### Follow-up Claude review fixes — 2026-10-29

- Disable configured Git clean, smudge, and process filters for task materialization and evidence collection. Materialize only after resolving filters in the new worktree context; preserve consistent unexpanded LFS/filter content and prevent task-selected attributes from launching host filter commands.
- Preserve task timeouts when later stream/file reads fail or an interrupt arrives during result parsing.
- Reclaim the probe's exact temporary files after confirmed termination, including timeout. Retain files and withhold task evidence when process termination or file cleanup is unresolved.
- Clarify unsupported evidence paths and index discrepancies. Keep default review behavior and intentional evidence limits unchanged.
- Validate 78 offline tests on Windows (76 passed, 2 platform skips), the native no-model task dry run, and a focused final probe-cleanup signal check. Claude's review completed with limited coverage: it read the runner and documentation but did not inspect the actual diff or tests.

### Bounded task connection recovery — 2026-10-29

- Allow one automatic task retry for the recognized `workspace routing discovery failed` startup stream, with `--connection-retries 0` to opt out. Reuse the same objective, model, settings, and worktree after a five-second delay within the original timeout budget.
- Require confirmed process-tree termination, no observed model/tool work or usage, no final response, and unchanged worktree, index/HEAD, ignored files, and scratch contents. Unknown or malformed diagnostics, partial work, timeout, interruption, and cleanup uncertainty prevent retry. Baseline inventory uncertainty disables recovery while allowing the initial task.
- Preserve the failed attempt's artifacts before starting another call and record the attempt history and retry count. Claude must keep polling the original invocation; it cannot reset the budget through another launch. Review-mode recovery remains unchanged.
- Validate 96 offline tests on Windows (94 passed, 2 platform skips), including 18 connection-recovery tests. The recorded routing failure is recognized without relaunching its task. Independent review and focused deadline, archive-failure, and identical-prompt checks passed; live connection recovery remains unverified.

### Claude review of connection recovery — 2026-10-29

- Preserve the original archive error when copying first-attempt diagnostics fails, instead of replacing it with a later directory-exists error. Keep partial artifacts and withhold retry.
- Preserve exception type and verification context after the retry delay. Skip the extra connection-classification scan when basic eligibility gates already rule out retry, report strict-classifier rejection, and remove the misleading unused effective-retries field.
- Clarify nonterminal recovery metadata, launched-retry counts, inventory bounds, and partial archives. Retain the exact failure classifier and final-message-file guard: the installed CLI's JSONL failure path does not emit an empty final-response file.
- Validate 98 offline Windows tests (96 passed, 2 platform skips). The two new regressions reproduced their failures before correction and passed afterward; independent remediation review passed. Claude reviewed the retry runner and tests at `f645451`, but did not inspect the patch itself or review the subsequent fixes.

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
