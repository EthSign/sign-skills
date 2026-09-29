## Speed & Parallelism (applies to every model)

- Optimize for wall-clock speed and token efficiency on every task, regardless of which model is running.
- Spawn subagents (Agent tool) for any independent piece of work — research, file sweeps, multi-file edits, test runs, reviews — and launch all independent agents in a single message so they run concurrently. Run them in the background unless the very next step depends on the result.
- Batch every independent tool call into one response (reads, greps, shell commands, MCP calls). Never issue sequential calls when they have no dependency on each other.
- Delegate codebase searches to the read-only search ladder below (`scout`, `explorer`, then `Explore`) and keep only the conclusion; do not read file dumps in the main context.
- When the user has opted into multi-agent orchestration (e.g. says "ultracode" or "use a workflow"), use the Workflow tool with pipeline/parallel fan-out rather than serial agents.
- Prefer the fastest tool that does the job: `rg` over `grep`, targeted file reads over full-project scans.
- Keep replies terse: lead with the result, skip narration and restatement.

## Subagent tiering (dynamic model + effort)

- Never delegate with the default general-purpose agent at session effort. Pick the cheapest tier that can do the job. Custom tiers live in `~/.claude/agents/` and use model aliases, which Claude Code resolves to the latest model in each family. The built-in Explore and Plan are the top rungs of their ladders. Both skip CLAUDE.md and cannot spawn agents. Plan inherits the session model and effort. Explore inherits the session model, capped at Opus.

  Read-only search ladder:

  | Agent | Model / effort | Use for |
  |---|---|---|
  | `scout` | haiku / low | single lookups: find a file, grep a symbol, read one fact |
  | `explorer` | sonnet / low | subsystem wiring, all call sites, module structure |
  | `Explore` (built-in) | session model, capped at opus | exhaustive multi-location or naming-convention sweeps |

  Planning ladder:

  | Agent | Model / effort | Use for |
  |---|---|---|
  | `planner` | opus / high | execution plans with per-step tier tags and parallel groups |
  | `Plan` (built-in) | session model / session effort | architecture trade-offs, plan-mode context gathering |

  Execution ladder:

  | Agent | Model / effort | Use for |
  |---|---|---|
  | `fast-worker` | haiku / low | edits with an exact spec, running commands or tests, formatting |
  | `std-worker` | sonnet / medium | most implementation: scoped or multi-file changes, tests, pattern-following edits |
  | `deep-worker` | opus / high | complex changes, unclear-root-cause debugging, design, migrations |
  | `verifier` | fable / max | adversarial review, security, root cause, judging designs, final checks |

- Sonnet 5.5 at medium outperforms the previous Sonnet at high on agentic coding, so send implementation to `std-worker` first and use `deep-worker` only for genuinely hard steps or after `std-worker` escalates.
- `verifier` runs on a different model from every worker, so its check is independent of the model that wrote the change.
- Composition: `planner`, `deep-worker`, and `verifier` may spawn `scout`, `explorer`, or `Explore` in parallel; `deep-worker` may also spawn `fast-worker`; `std-worker` may spawn `scout`. `scout`, `explorer`, and `fast-worker` never spawn. Nesting is capped at 3 levels by `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`.
- Built-in `Explore` and `Plan` accept the Agent tool's per-call `model` override but no effort override. When medium thoroughness is enough, use `explorer` rather than `Explore` with a model override, so effort drops too.
- For any task that needs a plan, spawn `planner` first, then execute each of its groups by launching the tagged tiers concurrently in one message, and finish with its verifier steps.
- Escalate on failure, not up front: if a tier returns `ESCALATE:` or an unconvincing result, rerun on the next rung with its output as context.
- Fan out: split work into independent slices and run many tier-1/tier-2 agents concurrently rather than one tier-3 agent serially. Reserve `verifier` for the merged result.
- In Workflow scripts, set `agentType` to one of these tiers and pass matching `model` and `effort` on every `agent()` call (`'low'` for mechanical stages, `'max'` for judge/verify stages).
