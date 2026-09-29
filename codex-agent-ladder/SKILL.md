---
name: codex-agent-ladder
description: Automatically route substantial implementation, debugging, codebase research, and review work among tiered Codex subagents with explicit model and reasoning settings, bounded escalation, and separate verification. Also install, update, verify, customize, or remove codex-agent-ladder.
---

# Codex Agent Ladder

Apply the ladder automatically to work within its description; no separate delegation request is needed. Use four roles at an appropriate level of capability. Select by task difficulty and consequence; keep quick, dependent steps in the main agent. These skill instructions request delegation within the user's task, subject to the host's permissions and available tools.

## Route work

| Role | Preset | Delegate when |
| --- | --- | --- |
| `ladder_scout` | `gpt-6-luna`, high | A bounded, read-only investigation can return useful evidence without filling the main context with search output. |
| `ladder_worker` | `gpt-6.1-sol`, medium | Implementation has a clear goal, established patterns, and a bounded set of owned files. |
| `ladder_deep_worker` | `gpt-6-astra`, high | Root cause, design, or migration decisions need substantial judgment. |
| `ladder_verifier` | `gpt-6.1-sol`, high | A consequential or complex result benefits from a separate review of its actual behavior. |

The installed TOML profiles are authoritative; the table describes shipped presets. Model access varies by host and account. Read only the profile needed for the current delegation.

- Plan and integrate in the main agent. Delegate independent investigations or implementation slices when the benefit exceeds startup and coordination costs. A one-command lookup or formatting change usually stays in the main agent.
- Start obviously difficult work at the deep tier. For ordinary implementation, start at the worker tier. A command or test runner does not need a separate model merely to execute it.
- Launch independent tasks together within the runtime's existing concurrency limit. Give concurrent writers disjoint file ownership, or separate worktrees when justified. Integrate changes before reviewing the combined result.
- Use a separate verifier context for complex or consequential changes, unresolved disagreements, or requested reviews. For a small routine change, the main agent's appropriate checks may suffice. Reviewer evidence and tests matter more than model identity.
- Keep delegation one level deep: the main agent coordinates; these four roles return results without spawning children. This is a workflow convention, not a change to runtime settings.

## Spawn a role

Prefer the host's native custom-agent selector when it is exposed. Personal profiles are in `<codex-home>/agents/ladder-*.toml`; project profiles are in `<project>/.codex/agents/`. Resolve Codex home from `CODEX_HOME`, then the user's `.codex` directory. Respect the host's configuration precedence.

If the spawn tool exposes model and reasoning overrides but no custom-agent selector, read the installed profile, or its corresponding [bundled profile](assets/subagents/) if uninstalled. Pass its `model` and `model_reasoning_effort` explicitly and include its `developer_instructions` in the delegated task. Use a fresh context with only necessary facts. If a history-fork option exists, choose the option compatible with explicit overrides; do not fork full history when that prevents model selection.

If the host cannot select a model, use an available inherited model and report that limitation when it affects the routing decision. Never claim a model was selected from the agent's self-description. Honor runtime overrides: read-only profile defaults may be replaced by the parent's live permissions. A read-only assignment still prohibits edits by instruction; it is not an additional sandbox guarantee in the fallback path.

Give each delegated task:

- The concrete outcome, relevant context, and acceptance criteria.
- Its scope and file ownership, existing user constraints, and appropriate validation.
- The expected response: evidence or changed files, checks performed and their results, and unresolved issues.

## Escalate and finish

Scouts and workers return `DONE`, `ESCALATE`, or `BLOCKED` with evidence. The verifier returns `PASS`, `FAIL`, or `UNCERTAIN`. Treat a reported success as a claim to validate.

- Escalate an incomplete scout investigation to the main agent or deep worker when judgment is needed. Escalate failed or uncertain worker implementation to the deep worker with the prior evidence and attempted checks.
- Allow one escalation per work item by default. If the deeper attempt still cannot satisfy the criteria, integrate what is useful and explain the remaining blocker or request the missing information. Do not repeat equivalent attempts.
- Missing permissions, credentials, dependencies outside the authorized scope, or an unavailable model are operational blockers. Diagnose them; greater reasoning effort does not grant access. Do not bypass permissions or silently substitute an unavailable model.
- Track each long-running command by its runtime session or process handle and wait on that same execution. Do not launch duplicate tests or builds because output is delayed. Use the host's supported wait tools.
- Inspect the integrated result and complete checks appropriate to the change. A verifier verdict does not authorize merging, deployment, publication, or messages to others.
- When comparing ladder performance, record observed elapsed time, escalations, checks, and runtime-reported model and usage metadata when available. Do not invent token counts, dollar savings, or quota equivalences. This skill provides routing conventions, not a hard spending limit.

## Manage the installation

For installation, updates, static verification, customization, or removal, read [installation.md](references/installation.md) and use `scripts/install.py`. Management requests do not require spawning subagents. The installer manages this skill's files, four profiles, its manifest, and a marked routing block in the active AGENTS.md guidance. It preserves unrelated instructions.
