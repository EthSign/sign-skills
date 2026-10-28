# Codex Delegator

Lets **Claude Code delegate implementation, testing, or independent review to Codex**, using the installed, authenticated Codex CLI. Review is the default and supports exact committed diffs, frozen working-tree changes, code-grounded questions, and standalone plans. Explicit `--mode task` lets Codex edit and test in a retained worktree, returning the changes for Claude to verify.

## Requirements and installation

- Python **3.10+**, standard library only; Git for repository reviews.
- A recent native Codex CLI supporting `exec --ignore-user-config --ignore-rules --ephemeral --output-schema --json`. Development compatibility was checked against `codex-cli 0.154.0-alpha.6.2`; 1.1.0 dry runs were checked against `codex-cli 0.154.0`.
- Authenticate the CLI yourself with `codex login`; the wrapper checks `codex login status`. Running the desktop app does not establish CLI authentication automatically.
- A bare `codex` (and `git`) resolves only from absolute PATH entries, never Windows' implicit current-directory lookup. Windows uses native `codex.exe`, not the npm `.cmd`/PowerShell shim. Supply `--codex-path` if needed. Python is an explicit dependency; the wrapper does not install it.
- One Python implementation targets Windows, macOS, and Linux. The 1.0.1 suite of 27 offline tests passed on macOS with Python 3.11 on 2026-10-14, and real runs have worked on macOS. The 1.1.0 suite (46 tests; 45 run on macOS, one is Windows-only) passed on macOS with Python 3.11 on 2026-10-14, as did no-model `--dry-run` checks against the real CLI. 1.1.0 has not yet been run on Windows or Linux or in a real model run; validate natively before claiming those platforms.

Copy this entire directory to `~/.claude/skills/codex-delegator/` for personal use, or `<project>/.claude/skills/codex-delegator/` for project-only use. Do not overwrite an existing customized installation without checking it. This repository copy alone is not an installation into Claude Code.

In Claude Code, invoke `/codex-delegator` or ask “Have Codex review these changes.” Skill layout and invocation follow the [Claude Code skills documentation](https://code.claude.com/docs/en/skills). No `allowed-tools` wildcard or permission bypass is installed. `agents/openai.yaml` is optional Codex catalog metadata, not a Claude permission setting.

For execution, ask “Have Codex implement this feature and run its tests, then check its work.” Claude chooses explicit task mode and supplies the objective, scope, and acceptance criteria.

## Usage

```sh
python3 scripts/invoke-codex.py --repo /path/to/repo \
  --base BASE_SHA --head HEAD_SHA --run-directory /path/to/new-review
python3 scripts/invoke-codex.py --repo /path/to/repo \
  --working-tree --run-directory /path/to/new-working-review
python3 scripts/invoke-codex.py --repo /path/to/repo \
  --head HEAD_SHA --prompt-file /path/to/document-and-question.md
python3 scripts/invoke-codex.py --prompt-file /path/to/plan.md \
  --model MODEL_ID --effort high --run-directory /path/to/new-plan-review
python3 scripts/invoke-codex.py --prompt "Is this migration order safe? ..."
```

Run from this skill directory, or use an absolute script path. In PowerShell, invoke a known Python executable with `& 'C:\path\python.exe' 'C:\path\invoke-codex.py'` and the same arguments. A supplied run directory must be outside the source repository and either nonexistent or empty; omitting `--run-directory` creates a durable temporary one. Every run prints `CODEX_DELEGATION_RUN_DIRECTORY=<path>` on stderr before preflight, and stdout carries a JSON summary including `run_directory` and `mode`. `--dry-run` performs local setup, compatibility checks, and cleanup without a model call (authentication is reported but not required for a dry run).

| Option | Behavior |
| --- | --- |
| `--mode review\|task` | Review is the default. Task requires a repository and objective, starts at `--head` or `HEAD`, and retains an editable worktree. Task rejects `--base` and `--working-tree`. |
| `--base`, `--head` | Exact endpoint diff at resolved commit IDs; head defaults to HEAD. No automatic merge-base substitution. |
| `--head` without `--base` | With `--repo` and an objective: **code-grounded** mode. Snapshots that exact commit with no diff so Codex can check a document or answer a question against the code. Never implied; `--repo` alone is refused. |
| `--working-tree` | Tracked changes relative to HEAD plus nonignored untracked files, frozen into a detached worktree. Cannot combine with `--base` or `--head`. |
| `--prompt-file` | Concise UTF-8 objective, question, or document (at most 1 MiB); without a repository, review only the supplied plan/text. |
| `--prompt` | The same objective inline; mutually exclusive with `--prompt-file`. Prefer the file for long, quoted, or multiline text. |
| `--run-directory` | Optional. New or empty directory outside the source repository, claimed exclusively; omitted creates a durable temporary directory. |
| `--model` | Optional exact model/alias. Default is Codex's built-in choice, **not** the model in user config. No silent fallback. |
| `--effort` | `low`, `medium` (default), `high`, or `xhigh`; the selected model must support it. |
| `--timeout-seconds` | Process guard, default 1800; no model-turn, tool-count, output-token, or finding-count cap. |
| `--codex-path` | Native executable path when not discoverable on absolute PATH entries. |

Structured output uses `codex exec` rather than the native `review` subcommand: this lets the wrapper specify exact two-endpoint diffs, a caller objective, and a stable JSON result together. Codex reads a patch and relevant snapshot files itself. See the official [non-interactive mode contract](https://learn.chatgpt.com/docs/non-interactive-mode).

### Implementation and testing tasks

```sh
python3 scripts/invoke-codex.py --mode task --repo /path/to/repo \
  --head FULL_SHA --prompt-file /path/to/task.md \
  --run-directory /path/outside/repo/task-unique
```

Task mode starts from the specified commit (`HEAD` by default). It does not copy uncommitted or ignored files from the source checkout. Codex works in `<run-directory>/worktree` with a restricted native permission profile, follows applicable project instructions, and can run relevant tests. It returns a structured summary, changed-file list, test outcomes, and limitations. Claude inspects the observed diff and new files before integrating the work.

The worktree and partial changes are retained on success, failure, timeout, and interruption. The wrapper never applies them to the original checkout. It separately saves `task-diff.patch`, new file bytes under `task-untracked/`, and hashes/actual changed paths in `task-evidence.json`. These observed artifacts let Claude check the model's claims. Ignored outputs stay in the worktree; exceeding the 64 MiB/250-untracked-file evidence limits makes the run incomplete without discarding work.

The task result is under `result.json.task`; existing review results remain under `result.json.review`. Task fields are `complete`, `summary`, `changed_files`, `tests` (each with `command`, `outcome`, and `details`), and `limitations`. Outcomes are `passed`, `failed`, or `not_run`. A completed wrapper run still needs parent verification of the objective and test results.

Task mode retains never-approve policy and suppression of web search, hooks, plugins, apps, additional agents, and host skills. Project instructions are enabled for implementation. The objective must explicitly authorize commits, pushes, publishing, or dependency installation; that restriction is a prompt instruction, not a command filter. Source and task worktrees share Git metadata. The sandbox is not a container or read-access boundary, and running tests executes repository code.

Task commands stay in the foreground. The wrapper stops the Windows job or original POSIX process group before collecting final logs and changes, even after successful parent exit. Windows job setup failure prevents execution; deliberately detached POSIX descendants are outside that process-group guarantee. See the task workflow for details.

Task scratch files use the retained `task-tmp/` directory. A fresh permission profile limits writes to the worktree and scratch directory, protecting sibling logs and results. Two no-model checks require profile selection and validation before execution; managed fallback or incompatible configuration blocks the task. This requires permission-profile support and `app-server --print-startup-config`. Task errors, timeouts, and interruptions retain their original cause and record later failures in `secondary_errors`; a failed termination check never becomes confirmed merely because its Windows job handle was closed.

See [the task workflow](references/task-mode.md) for scope selection, result verification, recovery, and cleanup. A task dry run also retains its prepared worktree; it does not contact a model.

### Code-grounded reviews

Use code-grounded mode to review a design document, answer a question, or check claims against the code at one commit. Put the document text, the question, and any context excerpts in the objective; Codex reads whatever snapshot files it needs. The prompt leads with the objective, then the snapshot location and the same read-only boundaries as the other modes. The review `summary` carries the direct answer. Findings cite repository-relative files with one-based lines, or an empty file and line 0 when they concern the supplied document or question rather than a code location. There is no diff and no `no_changes` result: a clean checkout still runs. This mode replaces the earlier workaround of cloning the repository, adding an untracked `REVIEW/` folder, and using `--working-tree`.

## Safety and scope

Review modes use the native **read-only sandbox**, never-approve policy, an empty execution directory, disabled web search, ignored user config/rules, and suppressed project instructions, hooks, plugins, apps, host skills, and additional agents. Code-grounded review uses the same controls. Read-only shell inspections are expected. Unexpected reported file-change, MCP, web-search, or delegation items make a review incomplete; task mode permits file-change events. This is diagnostic validation, not a substitute for sandbox enforcement. The wrapper does not impose a brittle “no shell” rule.

This is **not a hermetic container or read-access boundary**. Codex can read other files the native sandbox permits. Its service connection remains necessary, and reviewed content is sent to the configured model service. Machine-managed policy, authentication, environment, installed executables, and Git configuration remain trusted inputs. CLI controls are based on the [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference); a future CLI may change them. Do not bypass failures by granting full access. Use an independently isolated environment for hostile repositories or sensitive cross-tenant material.

Git snapshot preparation is outside the child sandbox and can use local Git filters; only use trusted Git configuration. In review mode, repository instructions are review data, and the model is instructed not to execute project code/tests/installers. That instruction is behavioral, whereas filesystem writes and command network restrictions depend on the native sandbox and applicable machine policy.

Preflight (`codex exec --help`, `codex --version`, `codex login status`) runs from a neutral temporary directory, and preflight and Git commands use file-backed output capture with a timeout and process-group (POSIX) or `taskkill /T` (Windows, from `%SystemRoot%\System32`) cleanup, so an inherited grandchild handle cannot stall the wrapper. The prompt reaches Codex through a temporary file rather than a pipe, so a large prompt cannot block past the timeout on Windows.

Working-tree mode includes staged/unstaged tracked content and nonignored untracked files; it does not preserve staging as a separate review dimension. A staged addition deleted from disk is refused because a collapsed final-state diff would omit it. The source and snapshot fingerprints must match before launch, and source drift after launch invalidates completion. Committed and code-grounded reviews use immutable commit IDs and do not depend on the caller's dirty checkout. Submodule repositories are refused. Working-tree evidence is capped at 64 MiB/250 untracked files, Git commands at 60 seconds. No evidence is silently truncated. An empty committed or working-tree scope reports `no_changes` without a model call; it is not a model review.

## Recovery and debugging

Every accepted run directory receives atomic terminal JSON and durable process logs:

| Artifact | Purpose |
| --- | --- |
| `.run-claim` | Exclusive claim holding the wrapper PID; a second caller cannot share the directory. |
| `status.json` | Live state, start-attempted/started flags, PID when known; terminal state after cleanup. |
| `preflight.json` | CLI version, requested settings, arguments, scope and hashes; present after successful preparation. |
| `stream.jsonl`, `stderr.log` | Direct child output, opened before launch. Can contain private source data. |
| `diff.patch`, `schema.json` | Exact repository patch (diff modes only) and final response contract. |
| `last-message.json` | Native last model message, retained even if invalid or incomplete. |
| `result.json` | Validated `review` or `task`, with a separate authoritative wrapper `complete` flag. |
| `metadata.json` | Final status, mode, usage, thread IDs, item counts, duration, scope hashes, cleanup diagnostics. |

A completed review requires successful process exit, a completed turn with reported positive output usage, valid final JSON declaring completion, and no reported failure/prohibited item. Require terminal `status.json.status=complete` as well as completion in both result and metadata. Zero findings are meaningful only for a complete review. There is no arbitrary maximum number of findings. Cost is `null`: the wrapper does not fabricate a dollar estimate from tokens. Requested model is not asserted to be the resolved model.

Atomic JSON replacement retries transient reader locks up to five attempts. Persistent publication failures become `artifact_error`, exit nonzero, and do not prevent attempts to publish the other artifacts. A bounded second publication pass propagates failure state to already-written files. The wrapper also emits `CODEX_DELEGATION_METADATA=<json>` on stderr, including start flags and per-file failures, for recovery when storage is unavailable. This failure record overrides stale files; it is never permission to retry a started model call. If timeout termination truncates JSONL, the primary status remains `timeout`; parse errors are retained separately and any valid final review is preserved as incomplete evidence.

SIGINT or SIGTERM ends the run with the terminal status `interrupted` and the error “Review interrupted; do not automatically retry”, not a generic `error`. After the first signal, the entry point ignores further SIGINT/SIGTERM, and final child cleanup, snapshot removal, and artifact publication always run with both signals ignored, so repeated termination requests cannot strand a snapshot or skip terminal artifacts.

Do not automatically retry after `codex_start_attempted=true`, including spawn ambiguity, timeout, interruption, missing output, or lost host task handles. Recover the existing run and seek approval for a new attempt. Native Codex may perform its own transport retries inside the single invocation. Failures before the run directory can be claimed (a nonempty, symlinked, or in-repository directory, or filesystem errors) cannot produce artifacts; the command exits 2. Other failures exit 1; completion/dry-run/no-changes exits 0. A dry run is never marked as a completed review.

Temporary review snapshots are removed through Git before deleting their owned temporary root. Cleanup ambiguity retains the directory, clears completion, and exits nonzero; any validated review text remains in the artifacts. Task worktrees are retained and reported through `task_worktree`/`worktree_retained`; their `cleanup_complete` flag concerns disposable runner files. Keep them until changes are integrated or discarding them is authorized, then remove them through Git worktree cleanup. User artifacts, including generated temporary run directories, are never automatically deleted. Protect and remove them according to your retention policy.

## Development

```sh
python3 -m unittest discover -s tests -v
```

Use a Python 3.10+ interpreter (for example `python3.11` where the system `python3` is older). Tests use fake child processes and disposable Git repositories; they do not contact Codex or consume model allowance. On POSIX, one test also runs the wrapper as a separate process behind a fake `codex` on PATH and sends it repeated SIGTERM. A real CLI dry-run verifies advertised flags but is not an authenticated end-to-end model test. See [CHANGELOG.md](CHANGELOG.md).

Version 1.2.0 was checked on Windows with Python 3.12 and `codex-cli 0.165.0-alpha.1.2`. Offline regression tests and the no-model task dry run passed. A real task invocation returned incomplete because the host execution policy blocked commands; successful live editing/testing and native macOS/Linux execution remain unverified for this release.
