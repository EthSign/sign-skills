# Changelog

All notable changes to Claude Agent Ladder are documented here.

## 1.0.0 - 2026-09-28

### Added

- Seven tiered Claude Code subagents: `scout` and `fast-worker` on Haiku,
  `explorer` on Sonnet at low effort, `std-worker` on Sonnet at medium,
  `planner` and `deep-worker` on Opus at high, and `verifier` on Fable at max.
- Routing rules for the global CLAUDE.md covering tier choice, escalation,
  nesting, and Workflow scripts.
- An idempotent Python installer with dry-run, conflict detection with
  backups, symlink-safe writes, an optional workflow size setting, and
  uninstall.
