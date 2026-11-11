# Changelog

All notable changes to Claude Agent Ladder are documented here.

## Unreleased

### Added

- `frontier-worker` (Fable, high effort), the tier above `deep-worker`, for
  open-ended or long-horizon slices and for `deep-worker` escalations. Fable
  5.2 costs $8 / $40 per million tokens, down from $10 / $50, and Anthropic
  recommends it when Opus 5.5 at higher effort still falls short.
- `cross-verifier` (Opus, max effort), which checks work written on Fable, so
  a risky change is still reviewed by a different model from its author.
- A fourth reason to delegate: a slice needs a stronger model than the session
  runs on.
- `BLOCKED:` as a status separate from `ESCALATE:`, for missing access,
  credentials, or dependencies that a stronger model would not fix.
- Rules for briefing a subagent, for who checks what, and for one escalation
  per slice. These follow the Codex Agent Ladder in this repository, as do
  the grouping of tiers by job and the treatment of tiers as presets.
- Tests that the routing table in `rules.md` matches the shipped agents, that
  read-only tiers cannot edit, and that only the tiers the rules name can
  spawn agents.

### Changed

- The tiers are regrouped by job, following Anthropic's "Building agents: when
  to fold subagents into your main agent loop": `scout` and `explorer`
  investigate, `std-worker`, `deep-worker`, and `frontier-worker` implement,
  and `verifier` and `cross-verifier` verify. `fast-worker` and `planner` are
  removed. The built-in `Plan` agent is no longer part of the ladder.
- `scout` is now for bulk mechanical reading run in parallel. Single lookups
  belong in the main session.
- The routing rules now start from the main session, which does lookups, small
  edits, and planning itself. Delegate only for context, parallelism,
  independent verification, or capability.
- A slice starts at the tier that fits it, so plainly hard work goes straight
  to `deep-worker`.
- Nesting is one level. `std-worker` and `deep-worker` can no longer spawn
  agents. `frontier-worker`, `verifier`, and `cross-verifier` may spawn
  `scout`, `explorer`, or `Explore`.
- `verifier` is for risky or hard-to-check changes written on Sonnet or Opus,
  not every change.
- Claude Code 2.1.321 or newer is required, because older builds resolve the
  `fable` alias to Fable 5.1.
- A search or context tool named in a project's CLAUDE.md or AGENTS.md is used
  first by the main session.
- Read-only mechanical Workflow stages use `scout`. Other mechanical stages
  may use `model: 'haiku'` with `effort: 'low'`.
- On update, the installer removes `fast-worker.md` and `planner.md` from
  `~/.claude/agents/` if you have not edited them. Edited copies are reported
  and left in place; `--force` removes them and keeps a `.bak` backup.

### Fixed

- The test suite now reads and writes files as UTF-8. On Windows, Python
  defaulted to cp1252, garbled the em-dashes in `rules.md`, and failed
  `test_fresh_install`. The installer was not affected.

### Documentation

- Windows notes in the README and SKILL.md: the `python3` Store stub, and the
  results of a test run on Windows 11.

## 1.0.0 - 2026-09-28

### Added

- Seven tiered Claude Code subagents: `scout` and `fast-worker` on Haiku,
  `explorer` on Sonnet at low effort, `std-worker` on Sonnet at medium,
  `planner` and `deep-worker` on Opus at high, and `verifier` on Fable at max.
- A waiting rule for the worker tiers, and the Monitor tool removed from every
  tier, so subagents block on long commands instead of arming repeated timers
  or starting duplicate test runs.
- Routing rules for the global CLAUDE.md covering tier choice, escalation,
  nesting, and Workflow scripts.
- An idempotent Python installer with dry-run, conflict detection with
  backups, symlink-safe writes, an optional workflow size setting, and
  uninstall.
