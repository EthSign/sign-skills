# Claude Agent Ladder

Claude Agent Ladder is a Claude Code-only skill that installs seven tiered subagents and the
routing rules that go with them. Each delegated task goes to the cheapest model
and effort that can do it, and escalates one tier only when the first one
reports that it needs more judgment. The authoritative agent instructions are
in [`SKILL.md`](SKILL.md). Release history is in [`CHANGELOG.md`](CHANGELOG.md).

## The tiers

Seven custom tiers cover three jobs: investigating, implementing, and
verifying. The main session does lookups, small edits, and planning itself.
The built-in `Explore` agent stays available as an option for exhaustive
searches; the built-in `Plan` agent is not part of the ladder.

| Job | Agent | Model / effort | Use for |
| --- | --- | --- | --- |
| Investigate | `scout` | haiku / low | Bulk mechanical reading that fans out: per-file extraction, classification, inventories. |
| Investigate | `explorer` | sonnet / low | Research that needs judgment: subsystem wiring, all call sites, module structure. |
| Investigate | `Explore` (built-in) | session model, capped at opus | Exhaustive multi-location or naming-convention sweeps. |
| Implement | `std-worker` | sonnet / medium | Most delegated implementation, parallel slices, mechanical edits, test runs. |
| Implement | `deep-worker` | opus / high | Hard slices: unclear root causes, complex multi-file changes, migrations. |
| Implement | `frontier-worker` | fable / high | Open-ended or long-horizon slices where a wrong design is costly, and `deep-worker` escalations. |
| Verify | `verifier` | fable / max | Independent review of risky or hard-to-check changes written on Sonnet or Opus. |
| Verify | `cross-verifier` | opus / max | The same review when the change was written on Fable. |

Why these choices:

- **Sonnet carries most of the work.** Sonnet 5.5 at medium effort beats the
  previous Sonnet at high on agentic coding, so delegated implementation goes
  to `std-worker` unless the slice is plainly hard.
- **Search runs at low effort.** Anthropic recommends low effort on Sonnet 5.5
  for search. Its known weakness at low effort, skipping checks after code
  changes, does not apply to a read-only agent.
- **Bulk reading uses Haiku.** Haiku 5.5 costs a twentieth as much per token
  as Sonnet 5.5 and is the fastest model in the lineup. `scout` does
  extraction that needs no judgment, usually as several scouts in parallel.
  Single lookups stay in the main session.
- **Hard work uses Opus.** Opus 5.5 costs half as much per token as Fable 5.2,
  and Anthropic recommends starting with it for most coding work.
- **Fable 5.2 is the top worker as well as a verifier.** Fable 5.2 costs $8 /
  $40 per million tokens, down from $10 / $50 for Fable 5.1, and scores above
  Opus 5.5 on Anthropic's own agentic coding benchmarks. Anthropic recommends
  it for demanding reasoning and long-horizon agentic work, or when Opus 5.5
  at higher effort still falls short. `frontier-worker` is that step: the tier
  `deep-worker` escalates to, and the starting tier for a slice that is
  open-ended from the start.
- **A risky change is checked by a different model from its author.**
  `verifier` is Fable at max effort and checks work written on Sonnet or Opus.
  Work written on Fable, by a Fable main session or by `frontier-worker`, goes
  to `cross-verifier`, which is Opus at max effort. Use either for risky or
  hard-to-check changes, not every change.
- **The tiers are presets, not a path every task climbs.** A slice starts at
  the tier that fits it. When one call needs a job at a different capability,
  the Agent tool's `model` override sets it for that call.
- **Mechanical Workflow stages use Haiku.** In a Workflow script, a read-only
  mechanical stage uses `scout`. Another mechanical stage can pass
  `model: 'haiku'` with `effort: 'low'`.
- **No tier can use Monitor.** A subagent that ends its turn ends its task, so it
  cannot wait for a background notification. Without this, a worker can arm
  timer after timer and start duplicate test runs. The worker tiers instead
  give long commands a long enough timeout, wait with one blocking loop, and
  never start a second copy of a command that is still running.

Nesting is one level. `frontier-worker`, `verifier`, and `cross-verifier` may
spawn `scout`, `explorer`, or `Explore` to gather evidence. `scout`,
`explorer`, `std-worker`, and `deep-worker` cannot spawn agents.

A tier that cannot finish says why. `ESCALATE:` means the work needs more
judgment, and the main session reruns it one tier up or takes it back.
`BLOCKED:` means access, credentials, or a dependency is missing, which a
stronger model would not fix. The verify tiers answer `CONFIRMED`, `REFUTED`,
or `UNCERTAIN`.

If a project names its own search or context tool in CLAUDE.md or AGENTS.md,
the main session uses it first.

## Why these tiers

The design follows Anthropic's article
[Building agents: when to fold subagents into your main agent loop](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop).
Most work belongs in the main loop. Subagents pay off for context isolation,
for parallel slices that each need a fresh context, and for independent
verification. This ladder adds a fourth case: handing one slice to a stronger
model than the session runs on. Extra tiers, deep nesting, and handoffs add
latency, lossy summaries, and routing mistakes, so each tier has to cover a
job no other tier does.

The first version had seven tiers, including `scout`, `fast-worker`, and
`planner`. `fast-worker` and `planner` are gone, because mechanical edits and
planning are faster done in the main session. `scout` was removed with them
and is back with a narrower job: bulk reading in parallel on Haiku 5.5, not
single lookups. `frontier-worker` and `cross-verifier` arrived with Fable 5.2.

Several conventions come from the
[Codex Agent Ladder](../codex-agent-ladder/) in this repository: tiers
grouped by job, presets instead of a fixed hierarchy, starting hard work at
the tier that fits it, `BLOCKED` as a status separate from `ESCALATE`, one
escalation per slice, and briefs that name the scope, the files a worker
owns, and the diff under review.

## Requirements

- Claude Code 2.1.321 or newer. The agents use model aliases, and older builds
  map `fable` to Fable 5.1, which costs more than Fable 5.2. If you cannot
  update, set `ANTHROPIC_DEFAULT_FABLE_MODEL=claude-fable-5-2`; that worked on
  2.1.316.
- Python 3.10 or newer (standard library only) to run the installer. On
  Windows, `python3` is often only the Microsoft Store stub; run the commands
  below with `py -3` or the full path to a real interpreter instead.
- Access to Fable for the `frontier-worker` and `verifier` tiers. On some
  plans Fable bills to usage credits instead of the plan's included limits,
  and `claude -p` bills them without asking. Without Fable, change `model` to
  `opus` in `frontier-worker.md` and `verifier.md` before installing; every
  check then runs on the same model as `deep-worker`.

Verified on 2026-11-11 with Claude Code 2.1.322 in a Sonnet session. The
models come from the run's usage report and each tier's own reply; the effort
is the configured value:

| Agent | Model | Effort |
| --- | --- | --- |
| `scout` | Haiku 5.5 | low |
| `explorer` | Sonnet 5.5 | low |
| `std-worker` | Sonnet 5.5 | medium |
| `deep-worker` | Opus 5.5 | high |
| `frontier-worker` | Fable 5.2 | high |
| `verifier` | Fable 5.2 | max |
| `cross-verifier` | Opus 5.5 | max |

The built-in `Explore` agent was last checked on 2026-09-28 with Claude Code
2.1.284, where it ran on Opus 5.5 at medium effort in a Fable session.

The installer and its test suite were also run on Windows 11 (Git Bash,
CPython 3.10.21, a checkout with `core.autocrlf=true`) on 2026-11-11. All 43
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
file you have not edited is updated in place, and new tiers are added.
Updating from the first seven-tier version also removes `fast-worker` and
`planner` from `~/.claude/agents/` and replaces `scout` with its new
definition, unless you edited them locally; the installer then reports them
and leaves them in place, and `--force` removes or replaces them and keeps a
backup. The rules block is replaced wholesale, so any edit you make between the
`claude-agent-ladder` markers is lost without a backup; put your own rules
outside the markers.

## Verifying

This spawns each tier and asks for its model. It makes one billed model call
per tier, two of them on Fable; the run recorded under
[Requirements](#requirements) cost $1.71:

```bash
claude -p "Use the Agent tool to spawn these subagent types concurrently in one message: scout, explorer, std-worker, deep-worker, frontier-worker, verifier, cross-verifier. Give each the prompt: 'Do not call tools. Reply with exactly one line: MODEL=<the model your system prompt says you are powered by>'. Report each reply as '<type>: <reply>', one per line." --max-turns 4
```

If `frontier-worker` or `verifier` reports Fable 5.1, Claude Code is older
than 2.1.321.

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
| `subagents/` | The seven Claude Code subagent definitions. |
| `scripts/install.py` | Installer, updater, and uninstaller. |
| `tests/` | Installer tests, and checks that the agents match the rules. |
| `agents/openai.yaml` | Skill metadata. |
