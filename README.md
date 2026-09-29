# Sign Skills

Reusable internal Codex and Claude Code skills for Sign projects.

## Available skills

| Skill | Purpose |
| --- | --- |
| [`architecture-diagram`](architecture-diagram/) | Creates polished dark-themed system, infrastructure, cloud, security, and network diagrams as self-contained HTML with inline SVG. |
| [`claude-agent-ladder`](claude-agent-ladder/) | Claude Code only. Installs tiered subagents and routing rules that send each delegated task to the cheapest model and effort that can do it, escalating on failure. |
| [`claude-delegator`](claude-delegator/) | Asks an installed Claude Code CLI for an independent, read-only second opinion on bounded analysis or code review tasks. |
| [`codex-delegator`](codex-delegator/) | Lets Claude Code ask the installed Codex CLI for an independent, read-only review of code changes or plans. |
| [`sign-slide-design`](sign-slide-design/) | Creates, redesigns, and reviews presentation decks against the official Sign deck design system. |

Each skill is self-contained and includes a reader-facing `README.md`, an agent-facing `SKILL.md`, metadata, and any references, scripts, or approved assets needed to do the work faithfully. Import details and third-party licensing are recorded in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and in the affected skill directory.

## Useful tools

| Tool | Purpose |
| --- | --- |
| [Recordly](https://github.com/webadderallorg/Recordly) | An open-source desktop screen recorder and editor for polished walkthroughs, demos, and product videos. |
| [Chatterbox](https://github.com/resemble-ai/chatterbox) | A family of open-source text-to-speech models for generating natural, expressive voices from text. |
