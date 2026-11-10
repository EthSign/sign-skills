# Changelog

All notable changes to Claude Delegator are documented here.

## 8.1.2 - 2026-11-10

Fixes from a review of 8.1.1.

### Fixed

- Repository reviews now pass `--restricted` and `--add-dir <evidence>`, so
  `Read`, `Glob`, and `Grep` are confined to the snapshot and evidence
  directories. The bare tool allow rule was not path-scoped, which let a
  prompt-injected diff ask the reviewer to read files elsewhere on the host.
  A CLI that does not advertise both flags stops in preflight.
- The review guidance names the frozen `changes.patch` and `manifest.json`.
  The reviewer has no shell, and earlier real runs reported that they could not
  run `git diff` and reviewed whole files instead. This is a pointer, not a
  guarantee: in the low-effort validation run below the bundled recipe still
  searched the snapshot instead of reading the patch.
- Empty or whitespace `--base-revision`/`--head-revision` values are refused.
  Two empty values previously selected the tool-less prompt-only route and could
  return a clean result for what the caller meant as a repository review.
- The executor's `.git`/`.claude` path refusal matches the way macOS and Windows
  resolve names: any letter case, trailing dots or spaces, ignorable Unicode
  code points, and 8.3 short names.
- SIGHUP is handled like SIGTERM in the review runner and the executor. A closed
  terminal previously killed the wrapper while Claude kept running with no
  timeout and a registered worktree.
- Snapshot Git commands no longer inherit `GIT_DIR`, `GIT_WORK_TREE`,
  `GIT_INDEX_FILE`, or the related object and namespace variables.
- Runner tests clear provider-override variables, so a developer's
  `ANTHROPIC_BASE_URL` no longer fails two of them.

### Added

- Diagnostic metadata `file_tool_confinement`, `out_of_snapshot_paths`, and
  `native_inspection_observed`. They do not change the completion status:
  Claude Code enforces the confinement, and some CLI versions do not stream the
  bundled reviewer's tool calls. Relative tool paths are now reported relative
  to the snapshot.

### Validation

- 90 offline tests (89 run on macOS; one is Windows-only) pass on macOS with
  Python 3.11 and 3.9. A no-model native `--dry-run` passed against Claude Code
  2.1.322.
- One real commit-range review ran through the wrapper on macOS with Claude
  Code 2.1.322 (`claude-opus-5-5`, `low` effort): `success_native_review`, the
  seeded bug was reported, both observed reads were inside the snapshot, and
  the snapshot was removed. It did not read `changes.patch`.
- A direct CLI probe with the wrapper's flags and a small model confirmed the
  confinement: with `--restricted --add-dir`, reads inside the working
  directory and the added directory succeeded and a read of a canary file
  outside both was denied; with the 8.1.1 flags the same canary read succeeded.
- Not exercised: `high` effort, working-tree mode in a real run, Windows, Linux.

## 8.1.1 - 2026-09-30

### Changed

- Default advisory reviews, collab conversation turns, and isolated Claude
  execution to Claude Opus 5.5 using the explicit `claude-opus-5-5` model ID.
- Keep `high` effort and explicit per-run model overrides; Fable remains
  available through `--model fable` or a full model ID.

## 8.1.0 - 2026-09-30

### Added

- Added opt-in Collab mode to the shared Python review runner. Conversation
  turns are bounded, prompt-only, and tool-free; a completion marker ends a
  turn but does not establish agreement.
- Added the collaboration workflow in `references/collab.md`: Codex and Claude
  agree on the full plan and one executor before substantive work, re-agree
  after material changes, and have the other model review the result.
- Added a separate Python 3.10+ Claude executor helper with `--restricted` and
  `--safe-mode` controls. It binds an agreement receipt hash to the full plan,
  executor, declared paths, and validation, and confines declared writes to an
  isolated temporary workspace for Codex to review, test, and integrate.
- Added offline executor coverage in `tests/test_executor.py`.

### Unchanged

- Advisory review remains the default and read-only, with the moving Fable
  model alias and high effort. The Python runner retains its existing recovery,
  limits, and platform requirements.

## 8.0.0 - 2026-09-17

### Changed

- Replaced the duplicated PowerShell and macOS implementations with one
  cross-platform Python 3.10+ standard-library implementation.
- **Breaking:** Removed `invoke-claude.ps1` and `invoke-claude.sh`. Invoke
  `python scripts/invoke-claude.py` (or `python3` / `py -3`) directly on every OS.
  Migrate PowerShell named parameters to kebab-case options, for example
  `-WorkingDirectory` to `--working-directory` and `-Model` to `--model`.
- Targeted Linux and macOS through the same Python entrypoint. This release was tested
  only on Windows, so POSIX support is not yet claimed as tested.
- Added `--prompt-file` for quoted, large, or multiline UTF-8 prompts without
  shell argument-quoting differences; preserve CRLF when Python reads that file.
- Made `--run-directory` optional. The runner creates a
  durable temporary directory when omitted and still accepts a nonexistent or
  existing empty directory when one is supplied.
- Preserved Fable/high defaults, three-dot commit-range semantics, evidence and
  Git limits, read-only isolation, durable recovery artifacts, and the rule
  against automatic retry after Claude start is attempted.
- Share bounded process-tree cleanup across model calls, CLI preflight and Git;
  shield final cleanup/publication from repeated termination signals and resolve
  executables without Windows' implicit current-directory lookup.

### Requirements

- Python 3.10 or newer is now required. Select the interpreter directly in the
  command; no launcher-specific environment variable or runtime installer is used.
- Windows still requires a native Claude executable instead of a `.cmd` or
  `.bat` shim. POSIX systems accept an executable Claude command or path.

### Fixed

- Pass native-review guidance through a temporary system-prompt file instead
  of argv so accepted prompts do not exceed OS command-line limits.
- Feed stdin from a temporary file and wait with a timeout, preventing Windows
  pipe writes from blocking indefinitely when Claude does not read input.
- Require an explicit boolean `loggedIn: true` during authentication preflight.
- Override submodule-ignore configuration consistently in evidence and changed
  path discovery, including staged changes and commit-range metadata.
- Normalize recovered text-block separators to LF across platforms.
- Reuse repository-root discovery and the initial HEAD lookup while retaining
  the final working-tree race check.
- Document and test that a failed Windows process-tree kill remains incomplete
  even if the direct parent exited; this does not prove descendants terminated.

### Development

- Added the portable regression command:
  `python -m unittest discover -s tests -p 'test_*.py' -v`.
- Validated 56 offline Python tests on Windows and a no-model CLI/snapshot dry
  run. Native Linux/macOS validation remains pending.
- Removed the obsolete shell/PowerShell tests and their mock, along with the
  compatibility-launcher test. Previous tracked files remain in Git history.
