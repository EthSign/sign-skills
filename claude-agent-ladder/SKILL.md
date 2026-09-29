---
name: claude-agent-ladder
description: Install, update, verify, or remove the Claude agent ladder, a set of tiered Claude Code subagents (scout, explorer, planner, fast-worker, std-worker, deep-worker, verifier) that route each delegated task to the cheapest model and effort that can do it, plus the routing rules that go with them in the user's global CLAUDE.md. Use when the user asks to set up, update, check, or uninstall the Claude agent ladder or tiered subagents. Claude Code only.
---

# Claude Agent Ladder

The agent ladder has two parts, and the installer manages both:

- Seven subagent definitions in `subagents/`, installed to `<claude-dir>/agents/`. Each pins a model alias and an effort level.
- The routing rules in `rules.md`, installed into `<claude-dir>/CLAUDE.md` between `<!-- claude-agent-ladder:begin -->` and `<!-- claude-agent-ladder:end -->`. They tell the orchestrating session which tier to pick, when to escalate, and which tiers may spawn which.

`<claude-dir>` is `$CLAUDE_CONFIG_DIR` when set, otherwise `~/.claude`.

## Install or update

1. Resolve `scripts/install.py` relative to this file and run it with Python 3.10 or newer. Pass `--workflow-size unrestricted` only if the user asked to lift the workflow size guideline. Use `--dry-run` first when the user wants to see the changes.

   ```bash
   python3 "$skill_dir/scripts/install.py"
   ```

2. Read the exit code and report each line of output that is not `unchanged`.
   - `0`: done.
   - `1`: some agent files were skipped because the user modified them or a different file already uses that name. List them and ask before rerunning with `--force`, which keeps a `.bak` copy and replaces them. If a skipped file is a symlink, say that `--force` overwrites the link's target.
   - `2`: an error, such as malformed `claude-agent-ladder` markers or an unclosed code fence in CLAUDE.md, a CLAUDE.md that is not valid UTF-8, or invalid JSON in settings.json. Report the error line. A CLAUDE.md problem is caught before anything is written.
3. Tell the user that running sessions picked up new agent definitions without a restart in testing, but read CLAUDE.md only at startup. Existing sessions need a restart, or a message asking them to re-read `<claude-dir>/CLAUDE.md`, to follow the new rules.

The installer is idempotent. Rerunning it after pulling a newer version of this skill updates every agent file the user has not edited.

## Verify

Spawning each tier and asking for its model confirms the definitions load. This makes a few small, billed model calls, so run it only when the user asks for verification:

```bash
claude -p "Use the Agent tool to spawn these subagent types concurrently in one message: scout, explorer, planner, fast-worker, std-worker, deep-worker, verifier. Give each the prompt: 'Do not call tools. Reply with exactly one line: MODEL=<the model your system prompt says you are powered by>'. Report each reply as '<type>: <reply>', one per line." --max-turns 4
```

Compare the result with the model table in `README.md`. A tier reporting an older model means the installed Claude Code maps that alias to an older release; updating Claude Code fixes it.

## Uninstall

```bash
python3 "$skill_dir/scripts/install.py" --uninstall
```

This removes the unmodified agent files, the rules block, and the manifest. It leaves `workflowSizeGuideline` in settings.json as it is.

## Customize

Do not edit installed agent files in place: an edited file blocks future updates to it. To change a tier for everyone, edit `subagents/` or `rules.md` in this skill and rerun the installer. To change one machine only, edit the installed agent file and accept that updates skip it. Never edit inside the rules block in CLAUDE.md: every install replaces it without a backup. Put machine-specific rules outside the markers.
