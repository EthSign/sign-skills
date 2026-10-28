# Changelog

All notable changes to Claude Agent Ladder are documented here.

## Unreleased

### Changed

- Seven tiers become four, following Anthropic's "Building agents: when to fold
  subagents into your main agent loop": `explorer`, `std-worker`,
  `deep-worker`, and `verifier` remain. `scout`, `fast-worker`, and `planner`
  are removed. The built-in `Plan` agent is no longer part of the ladder.
- The routing rules now start from the main session, which does lookups, small
  edits, and planning itself. Delegate only for context, parallelism, or
  independent verification.
- Nesting is one level. `std-worker` and `deep-worker` can no longer spawn
  agents; only `verifier` may, and only `explorer` or `Explore`.
- `verifier` is for risky or hard-to-check changes, not every change.
- A search or context tool named in a project's CLAUDE.md or AGENTS.md is used
  first by the main session.
- Mechanical Workflow stages may use `model: 'haiku'` with `effort: 'low'`.
- On update, the installer removes `scout.md`, `fast-worker.md`, and
  `planner.md` from `~/.claude/agents/` if you have not edited them. Edited
  copies are reported and left in place; `--force` removes them and keeps a
  `.bak` backup.

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
