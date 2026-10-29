---
name: codex-delegator
description: Delegate a bounded implementation or testing task from Claude Code to the installed Codex CLI, or request an independent read-only review of code, plans, documents, or code-grounded questions. Use when the user asks to have Codex implement, fix, test, investigate, or review work. Task execution is explicit; review remains the default.
---

# Codex Delegator

Use `scripts/invoke-codex.py` relative to this skill directory. This launches an independent Codex model, not a tool server. Claude remains responsible for scope, verification, and the final answer.

## Choose the workflow

- For implementation, fixes, or executing tests, use explicit `--mode task` and read [task delegation](references/task-mode.md). The user request to delegate that work supplies authorization; do not ask again merely because task mode writes files. Give Codex a bounded objective, permitted scope, acceptance criteria, and relevant validation commands.
- For review, inspection, or questions without executing project code, use the review workflow below. Omitting `--mode` selects review. Requests for a second opinion do not imply permission to edit.

Task mode creates a retained worktree from a commit, allows edits and relevant tests, and returns changes for Claude to inspect. It can automatically retry one recognized connection failure before any observed work, subject to the checks in the linked reference. The wrapper owns that retry; Claude must keep polling the same invocation and must not add another retry. The following review-only restrictions do not apply to task execution; its controls and recovery rules are in the linked reference.

## Review workflow

1. Confirm the bounded review target and choose one mode.
   - **Committed:** resolve explicit base/head commits and verify the intended PR head locally. `--base` means the exact endpoint diff, not an implicit merge base.
   - **Working tree:** `--working-tree` reviews uncommitted work: tracked changes and nonignored untracked files.
   - **Code-grounded:** to review a document or answer a question against the code, pass `--repo` and `--head FULL_SHA` with an objective and no `--base`/`--working-tree`. Codex reads a read-only snapshot of that exact commit; there is no diff. Put the document text and any context excerpts in the `--prompt-file` (at most 1 MiB). Do not clone the repository or add an untracked `REVIEW/` folder for this.
   - **Plan:** provide a concise UTF-8 objective without `--repo`.
2. Locate Python 3.10+ (`python`, `python3`, or a known full executable path), Git, and the native Codex executable. The wrapper resolves bare `codex` and `git` names only from absolute PATH entries, never the current directory. On Windows a `.cmd`/`.ps1` shim is insufficient: use `--codex-path` to the native `codex.exe`. Do not install dependencies, change authentication, or weaken sandbox settings automatically. CLI authentication is separate from whether a Codex desktop session is running.
3. Tell the user the scope before starting. `--run-directory` is optional. If you supply one, use a fresh absolute path outside the source repository; it may be nonexistent or an existing empty directory, and the wrapper claims it exclusively and refuses a nonempty one. If you omit it, the wrapper creates a durable temporary directory. Either way it prints `CODEX_DELEGATION_RUN_DIRECTORY=<path>` on stderr before preflight and `run_directory` in the final JSON; record that path. Keep the objective compact: use `--prompt` for a short inline objective or `--prompt-file` for long, quoted, or multiline text (not both). Do not paste the entire diff, repository, or chat. The wrapper materializes a detached snapshot and, in diff modes, supplies the exact patch path.
4. Run once. Default effort is `medium`; respect an explicit user model/effort request using `--model`/`--effort`. Omitted model uses the CLI built-in default because user config is ignored. Never silently substitute an unavailable model. The default process timeout is 30 minutes, with no arbitrary turn, tool-call, finding-count, or output-token cap. An explicit longer timeout can be selected before launch for a justified scope.
5. Preserve the host's live shell/background-task handle and poll it until completion. A host tool returning early is not a failed run. If the handle is lost, read `status.json`, `stream.jsonl`, and `stderr.log` in the recorded run directory; do not start a second process. If a process is still running, wait or obtain permission to terminate it.
6. Require `status.json.status=complete`, `metadata.json.complete=true`, and `result.json.complete=true` for a completed review. A timeout, interruption, failed turn, malformed stream, missing final JSON, source change, artifact error, or `review.complete=false` is incomplete, never clean. If writes fail, recover the `CODEX_DELEGATION_METADATA=` record from the tracked command's stderr; its `artifact_error` overrides any stale files. Partial findings can be inspected but must be labeled partial. No automatic retry after `codex_start_attempted=true`, and none after an `interrupted` status; ask for approval with the reason and proposed scope/settings. A preflight failure with both start flags false can be corrected without spending a model call.
7. Independently reproduce actionable findings. Do not fix, commit, push, post comments, or mark a PR ready merely because Codex suggested it. Those actions require the user's applicable authorization.
8. Finish with findings plus a short debug footer: status, mode, requested model/effort, exact base/head or code-grounded commit or other scope, diff hash (if any), elapsed time, reported token usage, item counts, cleanup status, and artifact path. In code-grounded mode, the review `summary` carries the direct answer; findings with an empty file and line 0 refer to the supplied document or question. Do not invent a dollar cost or infer actual model identity from the requested alias.

## Review commands

Substitute absolute paths and, when you choose one, a unique run directory. Resolve this skill's path from the loaded skill, not the caller's working directory.

```sh
python3 /path/to/codex-delegator/scripts/invoke-codex.py \
  --repo /path/to/repo --base FULL_BASE_SHA --head FULL_HEAD_SHA \
  --run-directory /path/outside/repo/review-unique

python3 /path/to/codex-delegator/scripts/invoke-codex.py \
  --repo /path/to/repo --working-tree \
  --model MODEL_ID --effort high --run-directory /path/outside/repo/review-unique

python3 /path/to/codex-delegator/scripts/invoke-codex.py \
  --repo /path/to/repo --head FULL_HEAD_SHA \
  --prompt-file /path/to/document-and-question.md

python3 /path/to/codex-delegator/scripts/invoke-codex.py \
  --prompt "Review this rollout plan for missing rollback steps: ..."
```

PowerShell uses the same arguments on one line: `& 'C:\path\python.exe' 'C:\path\invoke-codex.py' ...`. Use `--dry-run` for local preparation/compatibility checks without contacting the model; a dry run is not a review.

## Review boundaries

- The wrapper requests the native read-only sandbox and `approval_policy=never`; shell inspection is allowed inside that sandbox. Do not reject a review merely for using shell. Do not bypass host Claude permissions or fall back to an unsandboxed invocation.
- User config/rules, project instructions, web search, hooks, plugins, apps, delegation, and host skill discovery are suppressed by CLI controls; execution starts in a fresh directory outside the snapshot. These controls are not a separate container, filesystem read allowlist, or guarantee against every managed configuration layer. See [README.md](README.md) for the trust boundary and compatibility limits.
- Code-grounded mode keeps every one of those controls. It reads the whole tree at one immutable commit as reference evidence; it does not review a diff or show what changed.
- Snapshot preparation runs local Git under the caller's permissions. Git configuration and the installed executables must be trusted. Preflight and Git commands are time-bounded and their process trees are killed on timeout. Codex must not run project code/tests/installers or network commands; this is an inspection review, not a test run.
- Submodules are refused rather than silently omitted. Working evidence is limited to 64 MiB and 250 untracked files; untracked symlinks and out-of-tree paths are refused. Ignored files are not included. Do not broaden or silently truncate the scope to get past these gates.
- Artifacts can contain source, prompts, paths, and model output. Keep them private; do not upload them automatically. Retain them for recovery, including generated temporary run directories. Temporary snapshots are cleaned up; ambiguous cleanup is reported and retained for inspection. SIGINT/SIGTERM end the run as `interrupted`; final cleanup and artifact publication ignore repeated signals.
