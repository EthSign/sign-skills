# Sign Skills

Reusable internal Codex skills for Sign projects.

## Available skills

| Skill | Purpose | Source |
| --- | --- | --- |
| [`architecture-diagram`](architecture-diagram/) | Creates polished dark-themed system, infrastructure, cloud, security, and network diagrams as self-contained HTML with inline SVG. | Adapted from [`hstarorg/skills`](https://github.com/hstarorg/skills) (MIT), itself adapted from Cocoon AI's architecture diagram generator (MIT). |
| [`claude-delegator`](claude-delegator/) | Asks an installed Claude Code CLI for an independent, read-only second opinion on bounded analysis or code review tasks. | Imported from [`EthSign/claude-delegator-codex`](https://github.com/EthSign/claude-delegator-codex). |
| [`sign-slide-design`](sign-slide-design/) | Creates, redesigns, and reviews presentation decks against the official Sign deck design system. | Native Sign skill. |

Each skill is self-contained and includes its own trigger guidance, references, metadata, and any approved assets needed to do the work faithfully.

Repository-level evaluation fixtures live under [`evals/`](evals/). Import details and third-party licensing are recorded in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and in the affected skill directory.
