# Codex Agent Ladder

A Codex skill that installs four tiered subagents and automatically routes substantial implementation, debugging, codebase research, and review work to them. Installation enables the routing through a managed block in the active `AGENTS.md` guidance file. A separate delegation request is unnecessary; quick tasks remain in the main agent.

## Roles

| Role | Model / reasoning | Purpose |
| --- | --- | --- |
| `ladder_scout` | `gpt-6-luna` / high | Bounded read-only investigations returning evidence. |
| `ladder_worker` | `gpt-6.1-sol` / medium | Scoped implementation following established patterns. |
| `ladder_deep_worker` | `gpt-6-astra` / high | Difficult debugging, design, and migrations. |
| `ladder_verifier` | `gpt-6.1-sol` / high | Separate read-only review of an integrated result. |

These are configurable presets. Choose models and reasoning levels available to your account. The verifier uses a separate context and can share the worker's model family.

## Install

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

If a skill manager has already copied this directory, run its installed `scripts/install.py` once to enable the profiles and automatic routing. Copying skill files alone does not execute the installer.

## Routing and maintenance

The main agent plans and integrates. Independent tasks can run concurrently with disjoint file ownership; workers do not spawn further agents. Hard work can start at the deep tier, and ordinary work gets at most one escalation. Separate verification scales to the complexity and consequence of a change. Routing conventions do not enforce a hard spending limit or guarantee lower usage.

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
