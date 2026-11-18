# Codex Agent Ladder

A Codex skill that routes substantial implementation, debugging, codebase research, and review work through four roles. Use skill discovery with explicit model overrides, or install native profiles and a managed routing block in `AGENTS.md`. Once the skill applies, no separate delegation request is necessary; quick tasks remain in the main agent.

## Roles

| Role | Purpose |
| --- | --- |
| `ladder_scout` | Bounded read-only investigations returning evidence. |
| `ladder_worker` | Scoped implementation following established patterns. |
| `ladder_deep_worker` | Difficult debugging, design, and migrations. |
| `ladder_verifier` | Separate read-only review of an integrated result. |

For everyday coding and PR review, consider `gpt-6.2-sol`. For difficult cross-service debugging or design decisions, consider `gpt-6.2-astra`. With a 6.2 parent, its model and effort are the starting point for a child. Adjust either when the assignment warrants it and the host supports the choice. All four roles ship with model and effort unset. You can pin either setting in a role and let the ladder choose the other per task. [Role selection](SKILL.md#spawn-a-role). [GPT-6.2 release guidance](https://learn.chatgpt.com/docs/whats-new/gpt-62-astra-sol)

Consider `gpt-6.1-terra` for bounded visual reasoning, supported computer use, clear writing, and scoped code fixes, starting at medium effort when appropriate. Choose only model/effort combinations exposed by the host. See [OpenAI's model selection guidance](https://learn.chatgpt.com/docs/model-selection).

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
