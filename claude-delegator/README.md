# Claude Delegator

Claude Delegator is a cross-platform Codex skill that asks an installed Claude
Code CLI for an independent, read-only second opinion. It supports bounded
analysis, exact commit-range reviews, and frozen working-tree reviews.

Claude is advisory: Codex remains responsible for reproducing the findings,
rejecting unsupported claims, and deciding what to present or change. The
authoritative agent instructions are in [`SKILL.md`](SKILL.md).
Release history is in [`CHANGELOG.md`](CHANGELOG.md).

## Platform support

| Platform | Entrypoint | Runtime |
| --- | --- | --- |
| Any platform | `scripts/invoke-claude.py` | Python 3.10+ |

The Python implementation is shared across platforms. Linux and macOS are
targeted, but this release has been tested only on Windows. Invoke an installed
Python 3.10+ interpreter directly; no shell launcher or runtime installer is used.

## Requirements

- Codex with skill support.
- Python 3.10 or newer (standard library only).
- The native Claude Code CLI installed and authenticated.
- Git for repository review modes.
- Outbound network access for real Claude requests.

Verify Claude authentication before using the skill:

```bash
claude auth status
```

Windows requires a native Claude executable; `.cmd` and `.bat` launchers are
intentionally rejected. On POSIX systems, the Claude command or path must be
executable.

## Installation

Install this directory as the `claude-delegator` skill. From the Sign skills
repository, the open Agent Skills CLI can install it directly:

```bash
npx skills add EthSign/sign-skills --skill claude-delegator
```

For a manual installation, copy this entire directory to the Codex skills
directory. The Python scripts do not need executable permissions when invoked
through Python.

Whether installed automatically or manually, keep `SKILL.md`, `agents/`,
`scripts/`, and `tests/` together.

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

Codex follows [`SKILL.md`](SKILL.md), invokes the Python entrypoint, retains
the run directory, waits for the single Claude invocation, and independently
checks actionable findings.

## Direct runner usage

The shared Python entrypoint accepts the same kebab-case options on every OS:

```bash
python3 scripts/invoke-claude.py --working-directory /absolute/path/to/repo \
  --review-working-tree --run-directory /absolute/path/outside/repo/review-001 \
  --prompt "Review the current changes for regressions."
```

Use `python`, `py -3`, or an absolute Python executable path where appropriate.
Run artifacts must live outside the reviewed repository to avoid reviewing the
wrapper's own output.

A supplied run directory may be
nonexistent or an existing empty directory. If it is omitted, the runner
creates a durable temporary run directory and reports the path.

### Linux and macOS

Review an exact commit range:

```bash
python3 scripts/invoke-claude.py \
  --working-directory /absolute/path/to/repository \
  --base-revision <base-sha> \
  --head-revision <head-sha> \
  --run-directory /absolute/path/to/new-run-directory \
  --prompt "Review this change for correctness and security."
```

Review staged, unstaged, and untracked changes:

```bash
python3 scripts/invoke-claude.py \
  --working-directory /absolute/path/to/repository \
  --review-working-tree \
  --run-directory /absolute/path/to/new-run-directory \
  --prompt "Review the current changes for regressions."
```

Run bounded analysis with no repository tools:

```bash
python3 scripts/invoke-claude.py \
  --run-directory /absolute/path/to/new-run-directory \
  --prompt "Analyze this question using only the evidence in this prompt: ..."
```

For large or multiline input, replace `--prompt TEXT` with
`--prompt-file /path/to/prompt.txt`. These options are mutually exclusive.
Prompts are limited to 256 KiB. Native-review guidance uses Claude's
[`--append-system-prompt-file`](https://code.claude.com/docs/en/cli-reference#system-prompt-flags)
instead of argv; stdin is file-backed so a stalled reader cannot block the
runtime timeout. The temporary guidance file is removed with the snapshot.
If cleanup is uncertain, retained temporary files may include prompt text.

### Windows

```powershell
python .\scripts\invoke-claude.py `
  --working-directory C:\absolute\path\to\repository `
  --base-revision <base-sha> `
  --head-revision <head-sha> `
  --run-directory C:\absolute\path\to\new-run-directory `
  --prompt-file C:\absolute\path\to\prompt.txt
```

Use `--review-working-tree` instead of the revision parameters to review current
working-tree changes. Omit both to run bounded analysis. Use a UTF-8 prompt file
for quoted or multiline text to avoid shell argument-quoting differences.
For simple text, `--prompt "Review this change for regressions."` also works.

Run the Python entrypoint with its help option for the complete parameter list:

```bash
python3 scripts/invoke-claude.py --help
```

```powershell
python .\scripts\invoke-claude.py --help
```

## Review isolation and safety

Repository reviews run in a temporary detached worktree at the verified head.
Commit-range evidence uses three-dot (`base...head`) semantics from the merge
base of the supplied revisions.

Working-tree reviews freeze staged, unstaged, and validated untracked files into
that snapshot, then compare source and snapshot fingerprints before Claude
starts. The original checkout is never Claude's working directory.

The runner also enforces:

- read-only `Read`, `Glob`, and `Grep` tools for repository reviews;
- no tools or slash commands for bounded analysis;
- no inherited MCP servers, repository settings, browser, shell, or edit tools;
- evidence byte and untracked-file limits;
- per-Git-command and wall-clock timeouts;
- streamed-result validation and authentication-aware budget handling;
- trap/finally-based process, worktree, and temporary-directory cleanup.

The runner never asks Claude to edit code, post comments, or perform external
actions.

## Results and recovery

Successful human-readable runs print Claude's review followed by
`CLAUDE_DELEGATION_METADATA=<json>`. `--raw-json` returns structured output, and
`--dry-run` validates the planned invocation without starting Claude.

Every run directory, whether supplied or generated, contains:

- `status.json` — current or terminal run state and process information;
- `stream.jsonl` — Claude's original streamed output;
- `stderr.log` — captured Claude stderr;
- `result.json` — terminal review, completeness, and error state;
- `metadata.json` — scope, evidence hashes, usage, timing, and safety metadata.

These files are the recovery source if the controlling shell session is lost.
Failed reviews return nonzero and preserve any safely recovered evidence.
`MORE_FINDINGS_REMAIN` returns zero with `review_complete=false`; it is valid
partial output, not a clean or exhaustive review.
An empty repository scope returns zero with terminal `no_changes` and
`review_complete=true` without starting Claude. A dry run also returns zero
after preflight, but remains `review_complete=false` because no review ran.

Atomic artifact writes retry transient locks. Persistent storage failures mark
the run incomplete and still attempt the other terminal files. Recover the
metadata printed by the tracked command if files are stale or missing; an
artifact-error status overrides any older success record. Raw streams and model
output can contain source material or prompt excerpts even though metadata does
not store the prompt or authentication identity.

## Defaults and limits

- Model: moving `fable` alias; override per run with `--model opus` on any platform (aliases and full model IDs are accepted).
- Effort: `high`
- Maximum runtime: 30 minutes
- Evidence ceiling: 64 MiB
- Untracked-file ceiling: 250 files
- Git command timeout: 60 seconds

Claude.ai subscription authentication omits the API-equivalent dollar cap.
API keys and external provider overrides retain the requested cap, which
defaults to `$0.50`.

## Development

Run the portable Python suite on any supported platform:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

The Python suite uses fake children and disposable Git repositories; it makes
no model or network calls. See
[`SKILL.md`](SKILL.md) for the authoritative delegation and review contract.
