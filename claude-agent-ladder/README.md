# Claude Agent Ladder

Claude Agent Ladder is a Claude Code-only skill that installs four tiered subagents and the
routing rules that go with them. Each delegated task goes to the cheapest model
and effort that can do it, and escalates one rung only when that tier fails or
reports that it needs more judgment. The authoritative agent instructions are
in [`SKILL.md`](SKILL.md). Release history is in [`CHANGELOG.md`](CHANGELOG.md).

## The tiers

Four custom tiers cover the cases where delegating pays off. The main session
does lookups, small edits, and planning itself. The built-in `Explore` agent
stays available as an option for exhaustive searches; the built-in `Plan`
agent is not part of the ladder.

| Agent | Model / effort | Use for |
| --- | --- | --- |
| `explorer` | sonnet / low | Read-heavy research: subsystem wiring, all call sites, module structure. |
| `Explore` (built-in) | session model, capped at opus | Exhaustive multi-location or naming-convention sweeps. |
| `std-worker` | sonnet / medium | Most delegated implementation, parallel slices, mechanical edits, test runs. |
| `deep-worker` | opus / high | Hard slices: unclear root causes, complex multi-file changes, migrations. |
| `verifier` | fable / max | Independent review of risky or hard-to-check changes. |

Why these choices:

- **Sonnet carries most of the work.** Sonnet 5.5 at medium effort beats the
  previous Sonnet at high on agentic coding, so delegated implementation goes
  to `std-worker` first and `deep-worker` handles only hard slices and
  escalations.
- **Search runs at low effort.** Anthropic recommends low effort on Sonnet 5.5
  for search. Its known weakness at low effort, skipping checks after code
  changes, does not apply to a read-only agent.
- **Hard work uses Opus.** Opus 5.5 costs less than half as much per token as
  Fable and turns around faster.
- **The verifier is Fable at max effort.** It runs on a different model from
  every worker, so its check is independent of the model that wrote the
  change. Use it for risky or hard-to-check changes, not every change.
- **Mechanical Workflow stages may use Haiku.** In a Workflow script, a
  mechanical stage can pass `model: 'haiku'` with `effort: 'low'`. Claude Code
  sends no effort setting to Haiku 4.5, so the effort has no effect there.
- **No tier can use Monitor.** A subagent that ends its turn ends its task, so it
  cannot wait for a background notification. Without this, a worker can arm
  timer after timer and start duplicate test runs. The worker tiers instead
  give long commands a long enough timeout, wait with one blocking loop, and
  never start a second copy of a command that is still running.

Nesting is one level. Only `verifier` may spawn agents, and only `explorer` or
`Explore`, to gather evidence. `explorer`, `std-worker`, and `deep-worker`
cannot spawn agents.

If a project names its own search or context tool in CLAUDE.md or AGENTS.md,
the main session uses it first.

## Why four tiers

The design follows Anthropic's article
[Building agents: when to fold subagents into your main agent loop](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop).
Most work belongs in the main loop. Subagents pay off in three cases: context
isolation, parallel slices that each need a fresh context, and independent
verification. Extra tiers, deep nesting, and handoffs add latency, lossy
summaries, and routing mistakes. An earlier version had seven tiers, including
`scout`, `fast-worker`, and `planner`; lookups, mechanical edits, and planning
are faster done in the main session, so those tiers were removed.

## Requirements

- Claude Code 2.1.284 or newer. The agents use model aliases, and older builds
  map `sonnet`, `opus`, and `fable` to older model releases.
- Python 3.10 or newer (standard library only) to run the installer. On
  Windows, `python3` is often only the Microsoft Store stub; run the commands
  below with `py -3` or the full path to a real interpreter instead.
- Access to Fable for the `verifier` tier. Without it, change the verifier's
  `model` to `opus` before installing.

Verified on 2026-09-28 with Claude Code 2.1.284 in a Fable session:

| Agent | Model | Effort |
| --- | --- | --- |
| `explorer` | Sonnet 5.5 | low |
| `std-worker` | Sonnet 5.5 | medium |
| `deep-worker` | Opus 5.5 | high |
| `verifier` | Fable 5.1 | max |
| `Explore` (built-in) | Opus 5.5 | medium |
| Workflow stages that set `model: 'haiku'` | Haiku 4.5 | not sent |

The installer and its test suite were also run on Windows 11 (Git Bash,
CPython 3.10.21, a checkout with `core.autocrlf=true`) on 2026-09-28. All 39
tests pass, with 5 skipped: four symlink tests (Windows needs Developer Mode
or admin rights to create symlinks) and the POSIX file-mode test. A CRLF
checkout installs LF agent files with the same hashes as a macOS or Linux
checkout, and an existing CRLF CLAUDE.md keeps its line endings through
install and uninstall.

## Installation

Install this directory as the `claude-agent-ladder` skill, then run its installer:

```bash
npx skills add EthSign/sign-skills --skill claude-agent-ladder
```

```bash
python3 ~/.claude/skills/claude-agent-ladder/scripts/install.py
```

Adjust the second path if the skill landed elsewhere. You can also clone the
repository and run `claude-agent-ladder/scripts/install.py` from the clone. Once the
skill is installed, asking Claude Code to "install the Claude agent ladder" runs the
same steps.

The installer:

- copies the four files in `subagents/` to `~/.claude/agents/`;
- adds the rules in `rules.md` to `~/.claude/CLAUDE.md` between
  `<!-- claude-agent-ladder:begin -->` and `<!-- claude-agent-ladder:end -->`;
- records what it installed in `~/.claude/claude-agent-ladder.manifest.json`.

It never overwrites an agent file that you edited or that it did not install.
It skips that file, reports it, and exits with status 1. Rerun with `--force`
to replace it; a `.bak` copy is kept next to the file in `~/.claude/agents/`.

The installer writes through symlinks, so a CLAUDE.md or agent file kept in a
dotfiles repository stays linked. For a symlinked agent file, `--force`
overwrites the link's target, and the output names that target.

If CLAUDE.md contains malformed markers, an unclosed code fence, or text that is
not UTF-8, the installer stops with status 2 before writing anything.

| Option | Effect |
| --- | --- |
| `--dry-run` | Print every change without writing anything. |
| `--force` | Replace conflicting agent files, keeping a `.bak` copy. |
| `--workflow-size SIZE` | Set `workflowSizeGuideline` in settings.json: `small`, `medium`, `large`, or `unrestricted`. |
| `--no-rules` | Leave CLAUDE.md alone, on install and on uninstall. |
| `--claude-dir PATH` | Target another Claude config directory. Defaults to `$CLAUDE_CONFIG_DIR`, then `~/.claude`. |
| `--uninstall` | Remove the unmodified agents, the rules block, and the manifest. |

In testing with Claude Code 2.1.284, running sessions picked up changed models
and effort levels without a restart, but changed tool restrictions took effect
only in new sessions. Sessions also read CLAUDE.md only at startup. Restart
running sessions to get everything; asking one to re-read `~/.claude/CLAUDE.md`
covers the rules but not the tool restrictions.

## Updating

Pull the latest version of this skill and rerun the installer. Every agent
file you have not edited is updated in place. Updating from the seven-tier
version also removes `scout`, `fast-worker`, and `planner` from
`~/.claude/agents/`, unless you edited them locally; the installer then reports
them and leaves them in place, and `--force` removes them and keeps a backup.
The rules block is replaced wholesale, so any edit you make between the
`claude-agent-ladder` markers is lost without a backup; put your own rules
outside the markers.

## Verifying

This spawns each tier and asks for its model. It makes a few small, billed
model calls:

```bash
claude -p "Use the Agent tool to spawn these subagent types concurrently in one message: explorer, std-worker, deep-worker, verifier. Give each the prompt: 'Do not call tools. Reply with exactly one line: MODEL=<the model your system prompt says you are powered by>'. Report each reply as '<type>: <reply>', one per line." --max-turns 4
```

## Customizing

To change a tier for everyone, edit `subagents/` or `rules.md` here and ship a
new version. To change one machine, edit the installed agent file; the
installer then leaves it alone on later runs. Do not edit inside the rules
block: the next install replaces it. Add overriding rules outside the markers
instead.

Change one thing at a time, and compare a handful of real tasks, run twice
each, before and after the change. A single run says little about whether a
different model or effort level helps.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Layout

| Path | Contents |
| --- | --- |
| `SKILL.md` | Agent-facing install, verify, and uninstall steps. |
| `rules.md` | Routing rules added to the global CLAUDE.md. |
| `subagents/` | The four Claude Code subagent definitions. |
| `scripts/install.py` | Installer, updater, and uninstaller. |
| `tests/` | Installer tests. |
| `agents/openai.yaml` | Skill metadata. |
