# Claude Delegator

Claude Delegator is a cross-platform Codex skill that asks an installed Claude
Code CLI for an independent, read-only second opinion. It supports bounded
analysis, exact commit-range reviews, and frozen working-tree reviews.

Claude is advisory: Codex remains responsible for reproducing the findings,
rejecting unsupported claims, and deciding what to present or change.

## Platform support

| Platform | Entrypoint | Runtime |
| --- | --- | --- |
| macOS | `scripts/invoke-claude.sh` | Native system `/bin/bash` 3.2 |
| Windows | `scripts/invoke-claude.ps1` | Windows PowerShell 5.1 or PowerShell 7 |

The macOS entrypoint does not call PowerShell and does not require Homebrew,
`jq`, or Python. Linux is not currently a supported runtime target.

## Requirements

- Codex with skill support.
- The native Claude Code CLI installed and authenticated.
- Git for repository review modes.
- Outbound network access for real Claude requests.

Verify Claude authentication before using the skill:

```bash
claude auth status
```

The wrappers require a native executable. Windows `.cmd` and `.bat` launchers
are intentionally rejected.

## Installation

Install the complete repository as the `claude-delegator` skill.

On macOS:

```bash
git clone https://github.com/boyuanx/claude-delegator-codex.git \
  ~/.codex/skills/claude-delegator
chmod +x ~/.codex/skills/claude-delegator/scripts/invoke-claude.sh
```

On Windows PowerShell:

```powershell
git clone https://github.com/boyuanx/claude-delegator-codex.git `
  "$HOME\.codex\skills\claude-delegator"
```

If the repository is already cloned elsewhere, copy or link the entire folder
to the same skill location so `SKILL.md`, `agents/`, and `scripts/` remain
together.

## Use from Codex

Invoke the skill by name and describe the review scope:

```text
Use $claude-delegator to review my current working-tree changes.
```

```text
Use $claude-delegator to ask Claude for an independent review of the changes
between <base commit> and <head commit>.
```

```text
Use $claude-delegator to analyze this design question: <question and evidence>.
```

Codex follows [`SKILL.md`](SKILL.md), selects the platform entrypoint, retains
the run directory, waits for the single Claude invocation, and independently
checks actionable findings.

## Direct wrapper usage

The wrappers can also be invoked directly. A run directory must be new or
empty when supplied.

### macOS

Review an exact commit range:

```bash
./scripts/invoke-claude.sh \
  --working-directory /absolute/path/to/repository \
  --base-revision <base-sha> \
  --head-revision <head-sha> \
  --run-directory /absolute/path/to/new-run-directory \
  --prompt "Review this change for correctness and security."
```

Review staged, unstaged, and untracked changes:

```bash
./scripts/invoke-claude.sh \
  --working-directory /absolute/path/to/repository \
  --review-working-tree \
  --run-directory /absolute/path/to/new-run-directory \
  --prompt "Review the current changes for regressions."
```

Run bounded analysis with no repository tools:

```bash
./scripts/invoke-claude.sh \
  --run-directory /absolute/path/to/new-run-directory \
  --prompt "Analyze this question using only the evidence in this prompt: ..."
```

### Windows

```powershell
& .\scripts\invoke-claude.ps1 `
  -WorkingDirectory C:\absolute\path\to\repository `
  -BaseRevision <base-sha> `
  -HeadRevision <head-sha> `
  -RunDirectory C:\absolute\path\to\new-run-directory `
  -Prompt "Review this change for correctness and security."
```

Use `-ReviewWorkingTree` instead of the revision parameters to review current
working-tree changes. Omit both to run bounded analysis.

Run either entrypoint with its help option for the complete parameter list:

```bash
./scripts/invoke-claude.sh --help
```

```powershell
Get-Help .\scripts\invoke-claude.ps1 -Detailed
```

## Review isolation and safety

Repository reviews run in a temporary detached worktree at the verified head.
Working-tree reviews freeze staged, unstaged, and validated untracked files into
that snapshot, then compare source and snapshot fingerprints before Claude
starts. The original checkout is never Claude's working directory.

The wrappers also enforce:

- read-only `Read`, `Glob`, and `Grep` tools for repository reviews;
- no tools or slash commands for bounded analysis;
- no inherited MCP servers, repository settings, browser, shell, or edit tools;
- evidence byte and untracked-file limits;
- per-Git-command and wall-clock timeouts;
- streamed-result validation and authentication-aware budget handling;
- trap/finally-based process, worktree, and temporary-directory cleanup.

The wrappers never ask Claude to edit code, post comments, or perform external
actions.

## Results and recovery

Successful human-readable runs print Claude's review followed by
`CLAUDE_DELEGATION_METADATA=<json>`. `--raw-json` returns structured output, and
`--dry-run` validates the planned invocation without starting Claude.

When a run directory is supplied, it contains:

- `status.json` — current or terminal run state and process information;
- `stream.jsonl` — Claude's original streamed output;
- `stderr.log` — captured Claude stderr;
- `result.json` — terminal review, completeness, and error state;
- `metadata.json` — scope, evidence hashes, usage, timing, and safety metadata.

These files are the recovery source if the controlling shell session is lost.
Incomplete reviews return nonzero and preserve any safely recovered evidence.

## Defaults and limits

- Model: moving `fable` alias; override per run with `--model opus` on macOS or `-Model opus` on Windows (aliases and full model IDs are accepted).
- Effort: `high`
- Maximum runtime: 30 minutes
- Evidence ceiling: 64 MiB
- Untracked-file ceiling: 250 files
- Git command timeout: 60 seconds

Claude.ai subscription authentication omits the API-equivalent dollar cap.
API keys and external provider overrides retain the requested cap, which
defaults to `$0.50`.

## Development

Run the macOS regression suite with the system Bash:

```bash
/bin/bash -n scripts/invoke-claude.sh
/bin/bash tests/test-invoke-claude.sh
```

Run the Windows durability suite from PowerShell:

```powershell
& .\tests\test-durable-runs.ps1
& .\tests\test-failure-paths.ps1
```

The macOS suite uses a fake Claude executable and makes no network call. See
[`SKILL.md`](SKILL.md) for the authoritative delegation and review contract.
