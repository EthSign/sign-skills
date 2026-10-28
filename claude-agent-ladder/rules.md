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

Plan in the main session: write the plan on your first turn and revise it as results arrive. Use plan mode when the user should approve the plan first.

## Subagent tiers

- Never delegate with the default general-purpose agent at session effort. Pick the cheapest tier that can do the job. Custom tiers live in `~/.claude/agents/` and use model aliases, which Claude Code resolves to the latest model in each family.

  | Agent | Model / effort | Use for |
  |---|---|---|
  | `explorer` | sonnet / low | read-heavy research: subsystem wiring, all call sites, module structure |
  | `Explore` (built-in) | session model, capped at opus | exhaustive multi-location or naming-convention sweeps |
  | `std-worker` | sonnet / medium | most delegated implementation, parallel slices, mechanical edits, test runs |
  | `deep-worker` | opus / high | hard slices: unclear-root-cause debugging, complex multi-file changes, migrations |
  | `verifier` | fable / max | independent review of risky or hard-to-check changes |

- Sonnet 5.5 at medium outperforms the previous Sonnet at high on agentic coding, so send implementation to `std-worker` first and use `deep-worker` only for genuinely hard slices or after `std-worker` escalates.
- Use `verifier` for changes where a mistake is costly or tests cannot show correctness: security, data loss, concurrency, migrations, public interfaces, and final checks on multi-agent results. For routine changes, run the tests yourself. `verifier` runs on a different model from every worker, so its check is independent of the model that wrote the change.
- Nesting is one level. Only `verifier` may spawn agents, and only `explorer` or `Explore` to gather evidence. Every other tier does its own reading. Explore skips CLAUDE.md, cannot spawn agents, and accepts a per-call `model` override but no effort override, so use `explorer` when medium thoroughness is enough.
- Subagents cannot idle for background-task notifications, so no tier has the Monitor tool, and the worker tiers wait on long commands with one blocking loop instead of timers. The main session can run a long command in the background and wait for its completion notice; it should not poll it or start a second copy.
- Escalate on failure, not up front: if a tier returns `ESCALATE:` or an unconvincing result, rerun on the next rung with its output as context, or take the work back into the main session.
- In Workflow scripts, set `agentType` to one of these tiers and pass matching `model` and `effort` on every `agent()` call. Mechanical stages may drop to `model: 'haiku'` with `effort: 'low'`; judge and verify stages use `'max'`.
