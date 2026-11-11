## Speed & Parallelism (applies to every model)

- Optimize for wall-clock speed and token efficiency on every task, regardless of which model is running.
- Do the work in the main session by default. Lookups, single greps, reading a few files, small edits, and running a test are faster done directly than delegated: a subagent costs a written brief, a cold start, and a lossy summary.
- Batch every independent tool call into one response (reads, greps, shell commands, MCP calls). Never issue sequential calls when they have no dependency on each other.
- If the project names its own search or context tool in CLAUDE.md or AGENTS.md, use it in the main session before searching any other way or delegating a search.
- When the user has opted into multi-agent orchestration (e.g. says "ultracode" or "use a workflow"), use the Workflow tool with pipeline/parallel fan-out rather than serial agents.
- Prefer the fastest tool that does the job: `rg` over `grep`, targeted file reads over full-project scans.
- Keep replies terse: lead with the result, skip narration and restatement.

## When to delegate

Spawn a subagent only when at least one of these holds:

- **Context:** the work means reading far more than you need to keep, such as a subsystem map or every call site, and only the conclusion matters.
- **Parallelism:** the work splits into independent slices that can run at the same time, each in its own fresh context. Launch them all in one message, in the background unless the next step depends on them.
- **Independence:** a change needs a check by a different model than the one that wrote it.
- **Capability:** a slice needs a stronger model than the session is running on, and switching the whole session would cost more than handing off that slice.

Plan in the main session: write the plan on your first turn and revise it as results arrive. Use plan mode when the user should approve the plan first.

## Subagent tiers

- Never delegate with the default general-purpose agent at session effort. Pick the job first, then the cheapest tier for that job that can do it. Custom tiers live in `~/.claude/agents/` and use model aliases, which Claude Code resolves to the latest model in each family.

  | Job | Agent | Model / effort | Use for |
  |---|---|---|---|
  | Investigate | `scout` | haiku / low | bulk mechanical reading that fans out: per-file extraction, classification, inventories |
  | Investigate | `explorer` | sonnet / low | research that needs judgment: subsystem wiring, all call sites, module structure |
  | Investigate | `Explore` (built-in) | session model, capped at opus | exhaustive multi-location or naming-convention sweeps |
  | Implement | `std-worker` | sonnet / medium | most delegated implementation, parallel slices, mechanical edits, test runs |
  | Implement | `deep-worker` | opus / high | hard slices: unclear-root-cause debugging, complex multi-file changes, migrations |
  | Implement | `frontier-worker` | fable / high | open-ended or long-horizon slices where a wrong design is costly, and `deep-worker` escalations |
  | Verify | `verifier` | fable / max | independent review of risky or hard-to-check changes written on Sonnet or Opus |
  | Verify | `cross-verifier` | opus / max | the same review when the change was written on Fable |

- The tiers are starting presets, not rungs every task climbs. Start a slice at the tier that fits it: `std-worker` for most implementation, because Sonnet 5.5 at medium handles it, and `deep-worker` straight away for work that is plainly hard, rather than paying for a weaker attempt first. When a job needs a different capability for one call, pass the Agent tool's `model` override instead of picking the wrong job's tier.
- `frontier-worker` and `verifier` run on Fable, which costs more per token than Opus and on some plans bills to usage credits. Use `frontier-worker` when `deep-worker` escalates, or when the slice is open-ended from the start: an unknown root cause across systems, a design with many interacting constraints, a long unattended run. Routine implementation never needs it.
- Use a verify tier for changes where a mistake is costly or tests cannot show correctness: security, data loss, concurrency, migrations, public interfaces, and final checks on multi-agent results. For routine changes, run the tests yourself. Pick the tier on a different model from the author: `verifier` when the session or worker that wrote the change ran on Sonnet or Opus, `cross-verifier` when it ran on Fable. Workers check their own slice, the verify tier looks for risks and gaps, and you validate the integrated result; reuse check results from the same snapshot instead of rerunning them.
- Brief each subagent with the outcome and acceptance criteria, its scope and the files it owns, the checks to run, and what is already known or ruled out. Give concurrent writers disjoint files. For a review, name the diff or revision to judge.
- Nesting is one level. `frontier-worker`, `verifier`, and `cross-verifier` may spawn `scout`, `explorer`, or `Explore` to gather evidence; no other tier spawns agents. Explore skips CLAUDE.md, cannot spawn agents, and accepts a per-call `model` override but no effort override, so use `explorer` when medium thoroughness is enough.
- Subagents cannot idle for background-task notifications, so no tier has the Monitor tool, and the worker tiers wait on long commands with one blocking loop instead of timers. The main session can run a long command in the background and wait for its completion notice; it should not poll it or start a second copy.
- Treat a subagent's result as a claim to check. `ESCALATE:` means the work needs more judgment: rerun it one tier up with the earlier output as context, or take it back into the main session. Allow one escalation per slice, then rethink the approach instead of repeating it. A failure the worker understands gets a repair at the same tier; a failed command alone does not justify a costlier model. `BLOCKED:` means access, credentials, or a dependency is missing: a stronger model will not fix that, so resolve it or ask the user.
- In Workflow scripts, set `agentType` to one of these tiers and pass matching `model` and `effort` on every `agent()` call. Read-only mechanical stages use `scout`; other mechanical stages may pass `model: 'haiku'` with `effort: 'low'`; judge and verify stages use `'max'`.
