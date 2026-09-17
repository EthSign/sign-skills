# Codex Delegator

Lets **Claude Code ask Codex for an independent review**, using the installed, authenticated Codex CLI. Supports exact committed diffs, frozen working-tree changes, and standalone plans. It does not edit code or publish reviews.

## Requirements and installation

- Python **3.10+**, standard library only; Git for repository reviews.
- A recent native Codex CLI supporting `exec --ignore-user-config --ignore-rules --ephemeral --output-schema --json`. Development compatibility was checked against `codex-cli 0.154.0-alpha.6.2`.
- Authenticate the CLI yourself with `codex login`; the wrapper checks `codex login status`. Running the desktop app does not establish CLI authentication automatically.
- Windows uses native `codex.exe`, not the npm `.cmd`/PowerShell shim. Supply `--codex-path` if needed. Python is an explicit dependency; the wrapper does not install it.
- One Python implementation targets Windows, macOS, and Linux. Windows tests are run during development; macOS/Linux need native validation before claiming platform certification.

Copy this entire directory to `~/.claude/skills/codex-delegator/` for personal use, or `<project>/.claude/skills/codex-delegator/` for project-only use. Do not overwrite an existing customized installation without checking it. This repository copy alone is not an installation into Claude Code.

In Claude Code, invoke `/codex-delegator` or ask “Have Codex review these changes.” Skill layout and invocation follow the [Claude Code skills documentation](https://code.claude.com/docs/en/skills). No `allowed-tools` wildcard or permission bypass is installed. `agents/openai.yaml` is optional Codex catalog metadata, not a Claude permission setting.

## Usage

```sh
python3 scripts/invoke-codex.py --repo /path/to/repo \
  --base BASE_SHA --head HEAD_SHA --run-directory /path/to/new-review
python3 scripts/invoke-codex.py --repo /path/to/repo \
  --working-tree --run-directory /path/to/new-working-review
python3 scripts/invoke-codex.py --prompt-file /path/to/plan.md \
  --model MODEL_ID --effort high --run-directory /path/to/new-plan-review
```

Run from this skill directory, or use an absolute script path. In PowerShell, invoke a known Python executable with `& 'C:\path\python.exe' 'C:\path\invoke-codex.py'` and the same arguments. Run directories must be new and outside the source repository. `--dry-run` performs local setup, compatibility checks, and cleanup without a model call (authentication is reported but not required for a dry run).

| Option | Behavior |
| --- | --- |
| `--base`, `--head` | Exact endpoint diff at resolved commit IDs; head defaults to HEAD. No automatic merge-base substitution. |
| `--working-tree` | Tracked changes relative to HEAD plus nonignored untracked files, frozen into a detached worktree. Cannot combine with revision flags. |
| `--prompt-file` | Concise UTF-8 objective; without a repository, review only the supplied plan/text. |
| `--model` | Optional exact model/alias. Default is Codex's built-in choice, **not** the model in user config. No silent fallback. |
| `--effort` | `low`, `medium` (default), `high`, or `xhigh`; the selected model must support it. |
| `--timeout-seconds` | Process guard, default 1800; no model-turn, tool-count, output-token, or finding-count cap. |
| `--codex-path` | Native executable path when not discoverable on PATH. |

Structured output uses `codex exec` rather than the native `review` subcommand: this lets the wrapper specify exact two-endpoint diffs, a caller objective, and a stable JSON result together. Codex reads a patch and relevant snapshot files itself. See the official [non-interactive mode contract](https://learn.chatgpt.com/docs/non-interactive-mode).

## Safety and scope

The child uses the native **read-only sandbox**, never-approve policy, an empty execution directory, disabled web search, ignored user config/rules, and suppressed project instructions, hooks, plugins, apps, host skills, and additional agents. Read-only shell inspections are expected. Unexpected reported file-change, MCP, web-search, or delegation items make the result incomplete; this is diagnostic validation, not a substitute for sandbox enforcement. The wrapper does not impose a brittle “no shell” rule.

This is **not a hermetic container or read-access boundary**. Codex can read other files the native sandbox permits. Its service connection remains necessary, and reviewed content is sent to the configured model service. Machine-managed policy, authentication, environment, installed executables, and Git configuration remain trusted inputs. CLI controls are based on the [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference); a future CLI may change them. Do not bypass failures by granting full access. Use an independently isolated environment for hostile repositories or sensitive cross-tenant material.

Git snapshot preparation is outside the child sandbox and can use local Git filters; only use trusted Git configuration. Repository instructions are review data, not permission to run code. The model is instructed not to execute project code/tests/installers. That instruction is behavioral, whereas filesystem writes and command network restrictions depend on the native sandbox and applicable machine policy.

Working-tree mode includes staged/unstaged tracked content and nonignored untracked files; it does not preserve staging as a separate review dimension. A staged addition deleted from disk is refused because a collapsed final-state diff would omit it. The source and snapshot fingerprints must match before launch, and source drift after launch invalidates completion. Committed review uses immutable base/head IDs and does not depend on the caller's dirty checkout. Submodule repositories are refused. Working-tree evidence is capped at 64 MiB/250 untracked files, Git commands at 60 seconds. No evidence is silently truncated. An empty scope reports `no_changes` without a model call; it is not a model review.

## Recovery and debugging

Every accepted new run directory receives atomic terminal JSON and durable process logs:

| Artifact | Purpose |
| --- | --- |
| `status.json` | Live state, start-attempted/started flags, PID when known; terminal state after cleanup. |
| `preflight.json` | CLI version, requested settings, arguments, scope and hashes; present after successful preparation. |
| `stream.jsonl`, `stderr.log` | Direct child output, opened before launch. Can contain private source data. |
| `diff.patch`, `schema.json` | Exact repository patch (when relevant) and final response contract. |
| `last-message.json` | Native last model message, retained even if invalid or incomplete. |
| `result.json` | Validated review, with a separate authoritative wrapper `complete` flag. |
| `metadata.json` | Final status, usage, thread IDs, item counts, duration, scope hashes, cleanup diagnostics. |

A completed review requires successful process exit, a completed turn with reported positive output usage, valid final JSON declaring completion, and no reported failure/prohibited item. Require terminal `status.json.status=complete` as well as completion in both result and metadata. Zero findings are meaningful only for a complete review. There is no arbitrary maximum number of findings. Cost is `null`: the wrapper does not fabricate a dollar estimate from tokens. Requested model is not asserted to be the resolved model.

Atomic JSON replacement retries transient reader locks up to five attempts. Persistent publication failures become `artifact_error`, exit nonzero, and do not prevent attempts to publish the other artifacts. A bounded second publication pass propagates failure state to already-written files. The wrapper also emits `CODEX_DELEGATION_METADATA=<json>` on stderr, including start flags and per-file failures, for recovery when storage is unavailable. This failure record overrides stale files; it is never permission to retry a started model call. If timeout termination truncates JSONL, the primary status remains `timeout`; parse errors are retained separately and any valid final review is preserved as incomplete evidence.

Do not automatically retry after `codex_start_attempted=true`, including spawn ambiguity, timeout, missing output, or lost host task handles. Recover the existing run and seek approval for a new attempt. Native Codex may perform its own transport retries inside the single invocation. Filesystem failures before the run directory can be created cannot produce artifacts; the command exits 2. Other failures exit 1; completion/dry-run/no-changes exits 0. A dry run is never marked as a completed review.

Temporary snapshots are removed through Git before deleting their owned temporary root. Cleanup ambiguity retains the directory, clears completion, and exits nonzero; any validated review text remains in the artifacts. User artifacts are never automatically deleted. Protect and remove them according to your retention policy.

## Development

```sh
python3 -m unittest discover -s tests -v
```

Tests use fake child processes and disposable Git repositories; they do not contact Codex or consume model allowance. A real CLI dry-run verifies advertised flags but is not an authenticated end-to-end model test. See [CHANGELOG.md](CHANGELOG.md).
