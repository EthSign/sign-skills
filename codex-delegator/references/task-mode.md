# Task delegation

Use this workflow when Claude delegates implementation, fixes, or project test execution to Codex. Invoke the same `scripts/invoke-codex.py` with explicit `--mode task`.

## Prepare and run

1. Use Python 3.10+, Git, and an installed, authenticated native Codex CLI. On Windows use the native `codex.exe`, not a `.cmd` or `.ps1` shim. Do not install tools or change authentication automatically.
2. Specify the repository root and starting commit (`--head`, default `HEAD`). Task mode does not copy uncommitted or ignored files and rejects `--base` and `--working-tree`. Check whether the task depends on source checkout changes before choosing its starting commit. It also refuses submodules. Do not silently discard required input or commit the user's work just to satisfy this interface.
3. Put the objective, permitted files/components, acceptance criteria, and relevant test commands in `--prompt` or a UTF-8 `--prompt-file` (maximum 1 MiB). Include any additional context needed because the child does not inherit the conversation. State the scope to the user, then run once. Model and effort overrides use `--model` and `--effort`; defaults are the CLI built-in model and medium effort.

```sh
python3 /path/to/codex-delegator/scripts/invoke-codex.py \
  --mode task --repo /path/to/repo --head FULL_SHA \
  --prompt-file /path/to/task.md \
  --run-directory /path/outside/repo/task-unique
```

For example, the objective can be: "Fix the CSV parser's handling of quoted newlines. Limit edits to the parser and its tests. Preserve the public API. Add a regression test and run the parser test suite. Report the commands and results."

The run directory must be fresh or empty and outside the source repository; omission creates a durable temporary directory. Record `CODEX_DELEGATION_RUN_DIRECTORY` from stderr and retain the host process handle. Poll that execution until completion. A host timeout or lost handle is not permission to launch a duplicate. `--dry-run` prepares a retained worktree and checks CLI compatibility without a model call; it does not prove execution succeeded.

## Execution and result

Codex runs in `<run-directory>/worktree`, a detached Git worktree at the chosen commit, with a restricted native permission profile and `approval_policy=never`. It can edit and run relevant project tests. Applicable project instructions are loaded in task mode and cannot expand the delegated objective. Web search, hooks, plugins, apps, delegation, and host skill discovery remain suppressed. Execution ignores user config/rules. The prompt requires explicit objective authorization for commits, pushes, publishing, or dependency installation; those restrictions are behavioral, not separate command filters. Host and managed permissions still apply.

Each task gets a fresh [permission profile](https://learn.chatgpt.com/docs/permissions) extending `:workspace`. It makes ambient workspace roots and temporary directories read-only, then grants writes to the task worktree and `<run-directory>/task-tmp`; the parent artifact directory stays read-only to task commands. The child process and its shell commands receive `TEMP`, `TMP`, and `TMPDIR` pointing to that scratch directory. Inherited protections for Git and agent configuration remain in place. Do not override these controls or grant the parent directory write access.

Task mode requires CLI permission-profile support and `app-server --print-startup-config`. Two bounded checks run without a model call: an undefined-profile probe must return the exact expected configuration error, then the defined task profile must validate. This detects legacy selection or managed fallback before execution. These checks load user configuration because the app-server command lacks `--ignore-user-config`; an incompatible configuration blocks the task. Actual execution retains `--strict-config --ignore-user-config`. Unsupported profiles or policies stop the run without weakening restrictions. `task_permission_verified` records successful preflight; it does not prove that a live command ran.

On native Windows, task mode explicitly selects the [MXC sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox). Ignoring user configuration otherwise discards the configured Windows backend, which can leave every command blocked under `approval_policy=never`. MXC must be supported and allowed by machine policy; the wrapper does not fall back to a weaker backend or provision the legacy sandbox.

Windows task preflight also runs a small trusted Python probe with `-I -S` inside the same Job Object containment used for delegation. It reads the wrapper schema, checks temporary writes in the worktree and scratch directory, and requires writes to the artifact parent to be denied. It removes its own probe files and never executes repository code. Failure stops before a model starts. `task_execution_verified=true` confirms these native checks passed; it does not establish that the model completed the requested task. A Windows `--dry-run` includes this probe.

The worktree separates file edits from the source checkout but shares Git metadata with it. It is not a container or read-access boundary. Use trusted repository code/configuration; builds and tests execute that code. Do not claim that an objective's file scope is a filesystem allowlist. Codex must report a blocked action instead of weakening its sandbox.

Task snapshot creation and final evidence collection disable configured Git clean, smudge, and process filters. The wrapper resolves filter configuration in the new worktree before materializing files, so task-written attributes cannot invoke a configured filter during unsandboxed collection. Git LFS pointers and other filter-backed files are not expanded automatically; include any required content explicitly in the authorized task setup. Git's ordinary line-ending and encoding handling still applies. Review-mode filter behavior is unchanged.

Task commands must stay in the foreground and must not start persistent services. Before reading final logs or collecting evidence, the wrapper terminates the Windows task job or the original POSIX process group, including on normal exit. On Windows, the process starts suspended and joins the job before running; unsupported job assignment fails closed. POSIX process groups do not contain descendants that deliberately start a new session. This is lifecycle cleanup for trusted tasks, not hostile-process isolation. Recheck the retained files before integrating them if they may have changed since evidence collection.

The wrapper retains the worktree and task scratch directory even on success, failure, timeout, or interruption. It never applies changes to the source checkout. The terminal summary reports `task_worktree`, `worktree_retained`, `task_tmp_directory`, and `task_tmp_retained`; `cleanup_complete` refers to disposable runner files, not removal of the task output or scratch files.

- `result.json.task` contains `complete`, `summary`, `changed_files`, `tests` (command, outcome, details), and `limitations`. Test outcomes are `passed`, `failed`, or `not_run`. These are model reports to verify.
- `task-diff.patch` contains the observed tracked binary diff against the starting commit. `task-untracked/` contains nonignored new files, including binary content.
- `task-evidence.json` records actual changed paths, starting/current commits, and hashes independently of the model's claimed file list. Ignored files remain only in the retained worktree. Evidence limits are 64 MiB and 250 untracked files. Only regular nonignored untracked files are captured; symlinks, nested repositories, and staged additions subsequently deleted from disk are refused. Collection errors leave the task incomplete and preserve the worktree.
- `status.json`, `metadata.json`, `stream.jsonl`, and `stderr.log` preserve the lifecycle and diagnostics. Treat artifacts as private source material.

Require `status.json.status=complete`, `metadata.json.complete=true`, and `result.json.complete=true` for wrapper completion. Inspect the actual diff and new files, reproduce relevant validation, and check the objective before reporting the task achieved. Completion does not establish that every test passed. Integrate the changes only within the user's authorized scope, checking for source drift and conflicts.

## Recovery and cleanup

A timeout, interruption, malformed result, artifact error, or uncertain process termination is incomplete. Inspect the existing run and partial work before deciding what remains. `CODEX_DELEGATION_METADATA` on stderr is authoritative when artifact writes fail.

Task mode permits one wrapper-managed retry for a recognized connection failure before any observed work. The default is `--connection-retries 1`; set `0` to disable it. The retry waits five seconds, preserves the same objective, model, settings, and worktree, and shares the original timeout budget. This applies only to task mode, whose process-tree cleanup and retained worktree allow the wrapper to check the preceding attempt.

The currently recognized failure is `workspace routing discovery failed`, including its native reconnect and WebSocket-to-HTTPS fallback diagnostics. Other errors do not qualify merely because their text mentions a connection or timeout. The wrapper requires a valid event stream containing only recognized startup/connection diagnostics, confirmed process-tree termination, no final response, and unchanged worktree, Git index/HEAD, and scratch contents. Any model message, reasoning, command or tool event (including a started item), file change, usage report, unknown event, malformed output, timeout, interruption, or uncertain cleanup prevents retry. Missing usage alone never establishes that no work occurred. A connection error following partial work does not qualify.

The retry inventory includes ignored files and is capped at 64 MiB and 10,000 entries per tree. Unreadable paths, links/reparse points, unsupported entries, or exceeding this inventory disable recovery without blocking the initial task. `connection_retry_disabled_reason` explains an unavailable or changed baseline, or an event stream that fails the strict classifier after the basic retry gates pass. CLI diagnostic changes are rejected until their no-work semantics are verified. These checks establish no observed task work; they do not certify zero server-side processing or zero billable usage.

Keep polling the same wrapper invocation during recovery. `retry_wait` in `status.json` or `metadata.json` is nonterminal; a file's existence or `complete=false` does not mean the process has stopped. If the host handle is lost, recover the existing process and artifacts rather than launching a replacement. The wrapper preserves the first attempt's diagnostics before starting its one retry. Claude must not launch another wrapper to reset the budget or change models or permissions. If the retry fails, recover the existing run and obtain authorization for another attempt with the reason and proposed scope. Preflight errors with both start flags false may still be corrected without spending a model call.

Task metadata includes `connection_retry_count`, `connection_retry_reason`, and an `attempts` list. The count measures retry CLI processes actually launched; it is not permission to relaunch after a setup failure. Each attempt has an `attempts/attempt-N/attempt.json` summary; its `codex_started` flag distinguishes a launched CLI from setup stopped before launch. Before retry, `attempts/attempt-1/` also preserves its stream, stderr, status, metadata, and result diagnostics, plus the original lifecycle status in `lifecycle-status.json`. An archive failure can leave partial files; the original `attempt_artifact_error` remains in root metadata and prevents retry. Root artifacts describe the latest attempt; a successful second attempt may complete the task while the first failure remains available for inspection.

Outside this guarded connection recovery, the first concrete error, timeout, or interruption remains `status`; later collection, cleanup, or publication failures appear in `secondary_errors` and the corresponding named error fields. Check `artifact_errors` and `attempt_artifact_error` even when the preserved status is `timeout` or `interrupted`. Launch failure and termination uncertainty are distinct: a failed launch can still have confirmed cleanup, while closing a Windows job handle after a failed termination check never counts as confirmed termination.

After confirmed probe termination, the wrapper removes the probe's exact temporary filenames even if the child timed out before running its own cleanup. If termination is uncertain, it retains the files. If file removal fails, `task_probe_cleanup_error` explains the failure and task evidence is withheld so diagnostic files are not presented as model output.

Keep the retained worktree until its changes have been inspected and integrated or the user has authorized discarding them. It remains registered with the source repository: use Git worktree removal for cleanup after preserving needed files, and inspect ambiguous setup failures rather than deleting their directories blindly. Do not remove the run artifacts as part of routine runner cleanup.
