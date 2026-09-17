---
name: codex-delegator
description: Ask the installed Codex CLI for an independent, read-only review from Claude Code. Use when the user asks to ask Codex, get a Codex second opinion, or have Codex review a code diff or plan. Not for editing, publishing, or autonomous review loops.
---

# Codex Delegator

Use `scripts/invoke-codex.py` relative to this skill directory. This launches an independent Codex model, not a tool server. Claude remains responsible for scope, verification, and the final answer.

## Workflow

1. Confirm the bounded review target. For committed changes resolve explicit base/head commits and verify the intended PR head locally. `--base` means the exact endpoint diff, not an implicit merge base. For uncommitted work use `--working-tree`; it includes tracked changes and nonignored untracked files. For a plan, provide a concise UTF-8 `--prompt-file` without `--repo`.
2. Locate Python 3.10+ (`python`, `python3`, or a known full executable path), Git, and the native Codex executable. On Windows a `.cmd`/`.ps1` shim is insufficient: use `--codex-path` to the native `codex.exe`. Do not install dependencies, change authentication, or weaken sandbox settings automatically. CLI authentication is separate from whether a Codex desktop session is running.
3. Choose a fresh absolute `--run-directory` outside the source repository; **do not pre-create it**. Tell the user the scope and record this path before starting. The wrapper creates it exclusively and refuses reuse. Keep the objective compact; do not paste the entire diff, repository, or chat. The wrapper materializes a detached snapshot and supplies the exact patch path.
4. Run once. Default effort is `medium`; respect an explicit user model/effort request using `--model`/`--effort`. Omitted model uses the CLI built-in default because user config is ignored. Never silently substitute an unavailable model. The default process timeout is 30 minutes, with no arbitrary turn, tool-call, finding-count, or output-token cap. An explicit longer timeout can be selected before launch for a justified scope.
5. Preserve the host's live shell/background-task handle and poll it until completion. A host tool returning early is not a failed run. Read `status.json`, `stream.jsonl`, and `stderr.log` for recovery if the handle is lost; do not start a second process. If a process is still running, wait or obtain permission to terminate it.
6. Require `status.json.status=complete`, `metadata.json.complete=true`, and `result.json.complete=true` for a completed review. A timeout, failed turn, malformed stream, missing final JSON, source change, artifact error, or `review.complete=false` is incomplete, never clean. If writes fail, recover the `CODEX_DELEGATION_METADATA=` record from the tracked command's stderr; its `artifact_error` overrides any stale files. Partial findings can be inspected but must be labeled partial. No automatic retry after `codex_start_attempted=true`; ask for approval with the reason and proposed scope/settings. A preflight failure with both start flags false can be corrected without spending a model call.
7. Independently reproduce actionable findings. Do not fix, commit, push, post comments, or mark a PR ready merely because Codex suggested it. Those actions require the user's applicable authorization.
8. Finish with findings plus a short debug footer: status, requested model/effort, exact base/head or scope, diff hash (if any), elapsed time, reported token usage, item counts, cleanup status, and artifact path. Do not invent a dollar cost or infer actual model identity from the requested alias.

## Commands

Substitute absolute paths and a unique run directory. Resolve this skill's path from the loaded skill, not the caller's working directory.

```sh
python3 /path/to/codex-delegator/scripts/invoke-codex.py \
  --repo /path/to/repo --base FULL_BASE_SHA --head FULL_HEAD_SHA \
  --run-directory /path/outside/repo/review-unique

python3 /path/to/codex-delegator/scripts/invoke-codex.py \
  --repo /path/to/repo --working-tree \
  --model MODEL_ID --effort high --run-directory /path/outside/repo/review-unique

python3 /path/to/codex-delegator/scripts/invoke-codex.py \
  --prompt-file /path/to/plan.md --run-directory /path/to/review-unique
```

PowerShell uses the same arguments on one line: `& 'C:\path\python.exe' 'C:\path\invoke-codex.py' ...`. Use `--dry-run` for local preparation/compatibility checks without contacting the model; a dry run is not a review.

## Boundaries

- The wrapper requests the native read-only sandbox and `approval_policy=never`; shell inspection is allowed inside that sandbox. Do not reject a review merely for using shell. Do not bypass host Claude permissions or fall back to an unsandboxed invocation.
- User config/rules, project instructions, web search, hooks, plugins, apps, delegation, and host skill discovery are suppressed by CLI controls; execution starts in a fresh directory outside the snapshot. These controls are not a separate container, filesystem read allowlist, or guarantee against every managed configuration layer. See [README.md](README.md) for the trust boundary and compatibility limits.
- Snapshot preparation runs local Git under the caller's permissions. Git configuration and the installed executables must be trusted. Codex must not run project code/tests/installers or network commands; this is an inspection review, not a test run.
- Submodules are refused rather than silently omitted. Working evidence is limited to 64 MiB and 250 untracked files; untracked symlinks and out-of-tree paths are refused. Ignored files are not included. Do not broaden or silently truncate the scope to get past these gates.
- Artifacts can contain source, prompts, paths, and model output. Keep them private; do not upload them automatically. Retain them for recovery. Temporary snapshots are cleaned up; ambiguous cleanup is reported and retained for inspection.
