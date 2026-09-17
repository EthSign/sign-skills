# Changelog

## 1.0.1 — 2026-09-16

- Pin Git patch prefixes so user diff formatting cannot break snapshot application.
- Resolve temporary roots before containment checks and reject rooted finding paths using both Windows and POSIX path semantics.
- Retry transient atomic-write locks, attempt all terminal artifacts after persistent failures, and emit recovery metadata without mislabeling a started run as preflight-only.
- Preserve timeout status and partial results when event output is truncated or malformed.
- Add regression coverage for all five confirmed review findings and related recovery cases.

## 1.0.0 — 2026-09-16

- Add Claude Code-to-Codex read-only review delegation for exact commit ranges, working-tree changes, and plans.
- Add model/effort selection, structured findings without count caps, native sandbox controls, and a configurable 30-minute process guard.
- Preserve atomic status/results, raw event logs, scope fingerprints, usage/debug metadata, and explicit no-blind-retry recovery.
- Add a shared Python standard-library runner and offline regression tests; no automatic installation, login, or publishing.
