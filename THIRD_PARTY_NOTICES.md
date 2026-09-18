# Third-Party Notices

## Architecture Diagram

- Imported from [`hstarorg/skills`](https://github.com/hstarorg/skills) at commit [`5e61add65334868e73439498c14bd0b52348fef3`](https://github.com/hstarorg/skills/commit/5e61add65334868e73439498c14bd0b52348fef3).
- That upstream identifies the skill as an adaptation of [Cocoon AI's architecture-diagram-generator](https://github.com/Cocoon-AI/architecture-diagram-generator).
- Both upstream projects identify the covered work as MIT-licensed. The required notices are retained in [`architecture-diagram/LICENSE`](architecture-diagram/LICENSE).
- Sign adds Codex UI metadata; the imported skill instructions and template are otherwise unchanged.

## Claude Delegator

- Imported from [`EthSign/claude-delegator-codex`](https://github.com/EthSign/claude-delegator-codex) at commit `2238558772258900ecde4f3d4e542b5f5fd36b6c`.
- The source checkout did not contain a license file at import time.
- The original skill instructions, UI metadata, wrappers, and regression tests were imported unchanged. Version 8 replaces the duplicated wrappers and platform-specific tests with a local Python-only implementation and portable tests. The original files remain available in Git history.

## Codex Delegator

- New local implementation for Claude Code-to-Codex review delegation, following the recovery and scope conventions of the adjacent Claude Delegator skill.
- The Python runner and tests are newly implemented, not a copied third-party bridge or SDK. No additional third-party runtime package or license grant is introduced.
- Protocol and installation references are linked in [`codex-delegator/README.md`](codex-delegator/README.md).
