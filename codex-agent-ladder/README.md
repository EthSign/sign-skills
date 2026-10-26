# Codex Agent Ladder

A Codex skill that routes substantial implementation, debugging, codebase research, and review work through four roles. Use skill discovery with explicit model overrides, or install native profiles and a managed routing block in `AGENTS.md`. Once the skill applies, no separate delegation request is necessary; quick tasks remain in the main agent.

## Roles

| Role | Model / reasoning | Purpose |
| --- | --- | --- |
| `ladder_scout` | `gpt-6-luna` / high | Bounded read-only investigations returning evidence. |
| `ladder_worker` | `gpt-6.1-sol` / medium | Scoped implementation following established patterns. |
| `ladder_deep_worker` | `gpt-6-astra` / high | Difficult debugging, design, and migrations. |
| `ladder_verifier` | `gpt-6.1-sol` / high | Separate read-only review of an integrated result. |

These are starting presets, not a mandatory model hierarchy. Select among available models, including Sol 6.1 and newly exposed models, based on task difficulty, consequences, and total usage including retries. Workers may use higher reasoning effort than the parent. The verifier uses a separate context and can share the worker's model family. Fixed native profile settings take precedence over spawn overrides; use the explicit override path when selecting different settings for an assignment.

## Install

For skill-only installation without global guidance or native profiles:

```sh
npx skills add EthSign/sign-skills --skill codex-agent-ladder --agent codex --global --yes
```

Use a host with explicit spawn model and effort overrides. Invoke `$codex-agent-ladder` if needed. This mode uses bundled role instructions and does not require running the Python installer.

For native profiles and a managed global routing block:

Requires Python 3.11+ and a Codex client with subagent support. From this repository's checkout:

```sh
python codex-agent-ladder/scripts/install.py --dry-run
python codex-agent-ladder/scripts/install.py
```

The installer copies the skill and four profiles into the selected Codex home (`CODEX_HOME`, otherwise `~/.codex`) and adds automatic routing to `AGENTS.override.md` when it is nonempty, otherwise `AGENTS.md`. It preserves unrelated instructions, configuration, and existing customized agent files. Start a new chat to load the guidance and profiles.

For a project-scoped installation:

```sh
python codex-agent-ladder/scripts/install.py --project /path/to/repository
```

If a skill manager has already copied this directory, run its installed `scripts/install.py` only when native profiles and global routing guidance are desired. Copying skill files alone does not execute the installer.

## Routing and maintenance

The main agent plans and integrates, and can complete tightly coupled work without workers. Independent tasks can run concurrently with disjoint file ownership; workers do not spawn further agents. Choose capability independently from role. Understood failures get bounded repairs; unresolved reasoning can justify capability escalation. Handoffs identify the relevant snapshot and existing evidence, and verification responsibilities are assigned to avoid redundant checks. Routing conventions do not enforce a hard spending limit or guarantee lower usage.

Read-only roles are instruction constraints, not separate sandboxes. Both native and fallback workers inherit parent permissions.

```sh
python codex-agent-ladder/scripts/install.py --verify
python codex-agent-ladder/scripts/install.py --uninstall --dry-run
python codex-agent-ladder/scripts/install.py --uninstall
```

Updates and removal preserve customizations. Static verification makes no model calls. See [installation and maintenance](references/installation.md) for target options, conflict handling, customization, and runtime verification. [SKILL.md](SKILL.md) contains the agent-facing routing instructions.

## Validation

```sh
python -m unittest discover -s codex-agent-ladder/tests -v
```

The installer and tests use only the Python standard library. Tests cover automatic activation, personal and project targets, overrides, idempotency, updates, backups, preserved customizations, dry runs, verification, removal, and destination-link protection. Windows symlink tests need Developer Mode or the relevant privileges.

Live model routing and cost or latency improvements require separate runtime measurements. Installation tests cannot establish those outcomes.

## Provenance

New local implementation inspired by the adjacent Claude Agent Ladder proposal. The Codex profiles, installer, routing instructions, and tests were implemented for this skill; no third-party runtime package or license grant is introduced. See the repository's [third-party notices](../THIRD_PARTY_NOTICES.md) and the [official Codex subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents).
