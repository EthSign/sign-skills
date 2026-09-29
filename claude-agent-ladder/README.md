# Claude Agent Ladder

Claude Agent Ladder is a Claude Code-only skill that installs seven tiered subagents and the
routing rules that go with them. Each delegated task goes to the cheapest model
and effort that can do it, and escalates one rung only when that tier fails or
reports that it needs more judgment. The authoritative agent instructions are
in [`SKILL.md`](SKILL.md). Release history is in [`CHANGELOG.md`](CHANGELOG.md).

## The ladders

The tiers form three ladders. The built-in `Explore` and `Plan` agents are the
top rungs of the first two.

| Ladder | Agent | Model / effort | Use for |
| --- | --- | --- | --- |
| Search | `scout` | haiku / low | Single lookups: find a file, grep a symbol, read one fact. |
| Search | `explorer` | sonnet / low | Subsystem wiring, all call sites, module structure. |
| Search | `Explore` (built-in) | session model, capped at opus | Exhaustive multi-location sweeps. |
| Planning | `planner` | opus / high | Execution plans with a tier tag per step and parallel groups. |
| Planning | `Plan` (built-in) | session model / session effort | Architecture trade-offs and plan-mode context gathering. |
| Execution | `fast-worker` | haiku / low | Edits with an exact spec, running commands or tests, formatting. |
| Execution | `std-worker` | sonnet / medium | Most implementation: scoped or multi-file changes and tests. |
| Execution | `deep-worker` | opus / high | Complex changes, unclear root causes, design, migrations. |
| Execution | `verifier` | fable / max | Adversarial review, security, root cause, final checks. |

Why these choices:

- **Sonnet carries most of the work.** Sonnet 5.5 at medium effort beats the
  previous Sonnet at high on agentic coding, so implementation goes to
  `std-worker` first and `deep-worker` handles only hard steps and escalations.
- **Search runs at low effort.** Anthropic recommends low effort on Sonnet 5.5
  for search. Its known weakness at low effort, skipping checks after code
  changes, does not apply to a read-only agent.
- **Planning and hard work use Opus.** Opus 5.5 costs less than half as much
  per token as Fable and turns around faster.
- **The verifier is always Fable at max effort.** Final checks always use the
  strongest model, and never the model that wrote the change.
- **Haiku handles mechanical work.** It is the fastest and cheapest option for
  lookups and fully specified edits. The Haiku tiers set `effort: low` for
  consistency, but Claude Code sends no effort setting to Haiku 4.5, so it has
  no effect there.

- **No tier can use Monitor.** A subagent that ends its turn ends its task, so it
  cannot wait for a background notification. Without this, a worker can arm
  timer after timer and start duplicate test runs. The worker tiers instead
  give long commands a long enough timeout, wait with one blocking loop, and
  never start a second copy of a command that is still running.

Tiers may nest: `planner`, `deep-worker`, and `verifier` can spawn the search
tiers, `deep-worker` can also spawn `fast-worker`, and `std-worker` can spawn
`scout`. `scout`, `explorer`, and `fast-worker` cannot spawn agents.

## Requirements

- Claude Code 2.1.284 or newer. The agents use model aliases, and older builds
  map `sonnet`, `opus`, and `fable` to older model releases.
- Python 3.10 or newer (standard library only) to run the installer.
- Access to Fable for the `verifier` tier. Without it, change the verifier's
  `model` to `opus` before installing.

Verified on 2026-09-28 with Claude Code 2.1.284 in a Fable session:

| Agent | Model | Effort |
| --- | --- | --- |
| `scout`, `fast-worker` | Haiku 4.5 | not sent |
| `explorer` | Sonnet 5.5 | low |
| `std-worker` | Sonnet 5.5 | medium |
| `planner`, `deep-worker` | Opus 5.5 | high |
| `verifier` | Fable 5.1 | max |
| `Explore` (built-in) | Opus 5.5 | medium |
| `Plan` (built-in) | Fable 5.1 | session effort |

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

- copies the seven files in `subagents/` to `~/.claude/agents/`;
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
file you have not edited is updated in place. The rules block is replaced
wholesale, so any edit you make between the `claude-agent-ladder` markers is lost
without a backup; put your own rules outside the markers.

## Verifying

This spawns each tier and asks for its model. It makes a few small, billed
model calls:

```bash
claude -p "Use the Agent tool to spawn these subagent types concurrently in one message: scout, explorer, planner, fast-worker, std-worker, deep-worker, verifier. Give each the prompt: 'Do not call tools. Reply with exactly one line: MODEL=<the model your system prompt says you are powered by>'. Report each reply as '<type>: <reply>', one per line." --max-turns 4
```

## Customizing

To change a tier for everyone, edit `subagents/` or `rules.md` here and ship a
new version. To change one machine, edit the installed agent file; the
installer then leaves it alone on later runs. Do not edit inside the rules
block: the next install replaces it. Add overriding rules outside the markers
instead.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Layout

| Path | Contents |
| --- | --- |
| `SKILL.md` | Agent-facing install, verify, and uninstall steps. |
| `rules.md` | Routing rules added to the global CLAUDE.md. |
| `subagents/` | The seven Claude Code subagent definitions. |
| `scripts/install.py` | Installer, updater, and uninstaller. |
| `tests/` | Installer tests. |
| `agents/openai.yaml` | Skill metadata. |
