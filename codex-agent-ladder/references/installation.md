# Installation and maintenance

## Skill-manager installation without global guidance

Install with `npx skills add EthSign/sign-skills --skill codex-agent-ladder --agent codex --global --yes`. Skill discovery and the bundled role profiles support the explicit model-override path without installing native profiles or writing global AGENTS.md guidance. This mode requires a host exposing explicit spawn model and effort overrides. If automatic discovery does not select the skill, invoke `$codex-agent-ladder` explicitly. Do not run the Python installer for this mode. Leave unrelated global guidance unchanged; clearing it requires an explicit user request. Preserve and reconcile local customizations before skill-manager updates.

## Alternative native-profile installation

Requires Python 3.11+ (standard library only) and a Codex client with subagent support. Native profiles use the current standalone agent TOML format. Hosts exposing only model overrides can follow the fallback instructions in SKILL.md.

Resolve `scripts/install.py` relative to this skill. On Windows, use an actual Python executable or `py -3`; a Microsoft Store stub is insufficient. Substitute the absolute script path in these commands:

```sh
python /path/to/codex-agent-ladder/scripts/install.py --dry-run
python /path/to/codex-agent-ladder/scripts/install.py
python /path/to/codex-agent-ladder/scripts/install.py --verify
```

Default personal installation:

- `<codex-home>/skills/codex-agent-ladder/`: discoverable skill and its bundled resources.
- `<codex-home>/agents/ladder-*.toml`: four standalone custom agent profiles.
- `<codex-home>/codex-agent-ladder.manifest.json`: ownership and content hashes.
- A marked automatic-routing block in the active global `AGENTS.md` or `AGENTS.override.md`.

Codex home is `CODEX_HOME` when set, otherwise `~/.codex`. `--codex-dir PATH` targets another personal profile. For a repository pilot, use `--project PATH`: profiles and manifest go under `PATH/.codex/`, and the skill goes under `PATH/.agents/skills/codex-agent-ladder/`. These options are mutually exclusive.

The installer appends a short automatic-routing block to the active guidance file, preserving all text outside its markers. A nonempty AGENTS.override.md takes precedence; otherwise it uses AGENTS.md. It leaves config.toml, unrelated agents, and permission settings alone. The global block requests delegation automatically for substantial tasks; small tasks remain in the main agent. More specific project or user instructions and host limits still apply. Start a new chat after installation to load the new guidance and profiles. If the skill does not appear, restart Codex.

Ordinary requests use the ladder automatically. You can also name it explicitly, for example:

```text
Use $codex-agent-ladder to implement this feature. Delegate independent pieces,
give workers disjoint file ownership, and review the integrated result.
```

## Updates and conflicts

Run the installer from a newly obtained package to update. It replaces files only when their current hash matches the last managed version. Existing identical files are accepted without taking ownership if another tool created them. Edited or conflicting files are skipped and reported.

- Exit `0`: operation completed, or static verification matched the package.
- Exit `1`: conflicts or differences require attention; successfully installed files are still recorded.
- Exit `2`: invalid source, invalid manifest, unsafe path, or another installation error.

Use `--force` only when the user authorizes replacing the named conflicting files. It saves uniquely named `.bak` copies before replacement. It never follows destination symlinks or junctions, even with `--force`. Malformed profiles or manifest data are rejected during preflight.

`--dry-run` prints the planned changes and creates nothing. `--verify` checks installed file contents and the routing block against this package without making model calls; it does not prove account access, runtime discovery, model routing, or performance. A custom installed profile correctly appears as a difference. Edited routing blocks are preserved during updates unless replacement is authorized with --force.

## Customize

All four roles ship with model and reasoning effort unset. To pin either setting, add a top-level `model` or `model_reasoning_effort` field to the role’s TOML file. For example, adding only `model_reasoning_effort = "high"` to `ladder-verifier.toml` leaves model selection open. Choose values supported by your host. You can edit a native profile directly or customize a bundled profile before installing it.

On upgrade, the installer unpins profiles it can identify as exact copies from a release that shipped stock pins. If the manifest cannot establish which installer created a pinned profile, the upgrade preserves it for review. The installer preserves locally edited files and reports them for review. If a package update removes or changes an explicitly chosen pin from a customized bundle, the installer preserves the installed role file and reports the conflict. This includes pins that match former stock values. Use `--verify` to see which files differ from the package.

Scout and verifier roles avoid source edits by instruction. Native and fallback workers inherit parent permissions; `sandbox_mode` and `approval_policy` in a custom-agent profile do not create a separate permission boundary. The installer rejects these misleading profile fields. Configure enforcement on the parent session.

## Interrupted operations

The installer writes a validated `codex-agent-ladder.transaction.json` ownership journal before changing resources. After an interruption, rerun install or uninstall to reconcile ownership against the bytes actually present. If the installed script itself has been removed, run the command from an intact copy of this package with the same target. Uninstall does not require intact bundled resources. Recovery never replays resource writes over later edits. Files customized after interruption remain protected, and identical files that predated installation remain unowned. Run maintenance serially for a given target.

`--dry-run` and `--verify` report a pending journal without changing it. After recovery, normal conflict handling applies. Do not delete a pending journal to suppress the warning: it may be the only ownership record for a partial installation.

## Remove

```sh
python /path/to/codex-agent-ladder/scripts/install.py --uninstall --dry-run
python /path/to/codex-agent-ladder/scripts/install.py --uninstall
```

Removal deletes only manifest-owned files whose hashes still match and removes the unedited managed routing block. Customized files, edited routing blocks, and backups remain. The manifest retains the previous hashes of locally edited managed files. When an upgrade preserves a conflicting pin installed from a customized bundle, it releases ownership of that file. Empty directories may remain. Use the same `--project` or `--codex-dir` target used at installation.

## Validation and performance

The package includes installer tests:

```sh
python -m unittest discover -s /path/to/codex-agent-ladder/tests -v
```

Runtime verification is a separate model-consuming task. When requested, delegate a small read-only fixture using each available role and inspect runtime-reported model metadata when exposed. Self-reported model names are not proof of routing. Evaluate real work against an ordinary Codex baseline using elapsed time, recorded usage, escalations, and defects; static installation tests cannot establish savings.

Configuration references, checked October 26, 2026:

- [Custom Codex agents and model selection](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents)
- [Skill authoring and discovery](https://learn.chatgpt.com/docs/build-skills)

Inspired by [EthSign's Claude Agent Ladder](https://github.com/EthSign/sign-skills/tree/feat/agent-ladder/claude-agent-ladder); this package uses Codex profiles and runtime waiting tools.
