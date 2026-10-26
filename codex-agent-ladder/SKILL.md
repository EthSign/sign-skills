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

The table describes starting presets, not a mandatory model hierarchy. Optimize usage allowance per correctly completed task, including coordination, verification, and retries. Preserve correctness and complete the authorized scope. Read only the profile needed for the current delegation.

Select from the models actually exposed by the current host. Current examples include `gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna`, and `gpt-6-astra`; older Sol, Terra, and Luna models remain options when available and appropriate. This is not an exhaustive allowlist. Include newly exposed models using their runtime descriptions and supported effort levels; do not invent model IDs or assume availability or relative cost from a name. Consult current official documentation when a material capability or pricing distinction is unclear. Do not favor Terra/Luna, or a newer model merely for being newer. Match capability and effort to complexity, uncertainty, consequences, and expected total usage.

Sol and Astra workers are authorized when justified, without a separate exception. Workers may use higher effort than the parent, including Astra/high under Astra/low. Use low for straightforward extraction, medium for exploration, and high for complex logic or substantial uncertainty; higher supported efforts are appropriate when their expected benefit justifies the usage. Keep the main agent's selected model and effort unchanged. If asked to recommend a main model, use the same selection criteria.

- Plan and integrate in the main agent. Delegate independent investigations or implementation slices when the benefit exceeds startup and coordination costs. A one-command lookup or formatting change usually stays in the main agent.
- Start obviously difficult work at the deep tier. For ordinary implementation, start at the worker tier. A command or test runner does not need a separate model merely to execute it.
- Launch independent tasks together within the runtime's existing concurrency limit. Give concurrent writers disjoint file ownership, or separate worktrees when justified. Integrate changes before reviewing the combined result.
- Start with up to two workers; add more when each has a distinct, bounded assignment and the time or quality benefit justifies the usage. While workers run, advance separate work in the main agent. Keep dependent steps sequential, avoid duplicate exploration, and do not create work merely to occupy agents.
- Use a separate verifier context for complex or consequential changes, unresolved disagreements, or requested reviews. For a small routine change, the main agent's appropriate checks may suffice. Reviewer evidence and tests matter more than model identity.
- Keep delegation one level deep: the main agent coordinates; these four roles return results without spawning children. This is a workflow convention, not a change to runtime settings.

## Spawn a role

Prefer the host's native custom-agent selector when it is exposed. Personal profiles are in `<codex-home>/agents/ladder-*.toml`; project profiles are in `<project>/.codex/agents/`. Resolve Codex home from `CODEX_HOME`, then the user's `.codex` directory. Respect the host's configuration precedence.

Native custom profiles with fixed model and effort fields take precedence over spawn overrides. Use a native profile only when its effective settings fit the assignment. When explicit model and effort overrides are exposed, use them with the relevant installed or [bundled profile](assets/subagents/)'s role instructions if a different configuration fits better. Explicitly pass the chosen model and effort; do not accidentally inherit the parent's settings. Use a fresh context with only necessary facts. If a history-fork option exists, choose the option compatible with explicit overrides; do not fork full history when that prevents model selection. Do not silently rewrite persistent profiles to make a one-off choice.

If an autonomously chosen model is unavailable, disclose the substitution and select another available model using the same criteria, or continue locally when practical. Preserve explicit user model and named-agent requirements; do not silently substitute for them. If the host cannot select a model, report that limitation and use an inherited model only when compatible with those requirements and justified by the expected benefit. Never claim a model was selected from the agent's self-description. Honor runtime overrides: read-only profile defaults may be replaced by the parent's live permissions. A read-only assignment still prohibits edits by instruction; it is not an additional sandbox guarantee in the fallback path.

Give each delegated task:

- The concrete outcome, relevant context, and acceptance criteria.
- Its scope and file ownership, existing user constraints, and appropriate validation.
- A concise response with evidence or changed files, file/line references or source links, checks and actual results, and explicit uncertainties. Keep prompts, tool output, and reports focused on relevant evidence.

## Escalate and finish

Scouts and workers return `DONE`, `ESCALATE`, or `BLOCKED` with evidence. The verifier returns `PASS`, `FAIL`, or `UNCERTAIN`. Treat a reported success as a claim to validate.

- Escalate an incomplete scout investigation to the main agent or deep worker when judgment is needed. Escalate failed or uncertain worker implementation to the deep worker with the prior evidence and attempted checks.
- Allow one escalation per work item by default. If the deeper attempt still cannot satisfy the criteria, integrate what is useful and explain the remaining blocker or request the missing information. Do not repeat equivalent attempts.
- Missing permissions, credentials, or dependencies outside the authorized scope are operational blockers. Diagnose them; greater reasoning effort does not grant access. Handle unavailable models according to the selection and disclosure rules above.
- Track each long-running command by its runtime session or process handle and wait on that same execution. Do not launch duplicate tests or builds because output is delayed. Use the host's supported wait tools.
- Use completion notifications or bounded waits rather than frequent polling. Verify consequential findings against sources or focused checks without repeating all supporting work. Complete required project checks; broaden or repeat checks only when changes, failures, or unresolved concerns justify it.
- Inspect the integrated result and complete checks appropriate to the change. A verifier verdict does not authorize merging, deployment, publication, or messages to others.
- When comparing ladder performance, record observed elapsed time, escalations, checks, and runtime-reported model and usage metadata when available. Do not invent token counts, dollar savings, or quota equivalences. This skill provides routing conventions, not a hard spending limit.

## Manage the installation

For installation, updates, static verification, customization, or removal, read [installation.md](references/installation.md). Management requests do not require spawning subagents. Support both skill-manager installation with bundled-profile fallback and the separate Python installer for native profiles and a managed global routing block. Honor the user's chosen installation mode: when they request skill-only guidance, do not run the Python installer or add global routing instructions. Skill-manager updates may replace local customizations; preserve and reconcile them when updating. Explicit task instructions and required project workflows take precedence over these defaults.
