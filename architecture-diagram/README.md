# Architecture Diagram

Create polished dark-themed system, infrastructure, cloud, security, and network architecture diagrams as standalone HTML files with inline SVG.

## When to use it

Use this skill for technical diagrams that need to communicate components, boundaries, dependencies, and directional flows. It is not intended for statistical charts, generic illustrations, or slide decks.

The generated file includes:

- a responsive dark technical theme;
- semantic colors for frontend, backend, data, cloud, security, and messaging components;
- inline SVG architecture graphics;
- summary cards and a legend; and
- built-in actions for copying or exporting the diagram as PNG or PDF.

## Use from Codex

```text
Use $architecture-diagram to map our gateway, services, event bus, databases, and trust boundaries.
```

Codex follows [`SKILL.md`](SKILL.md), adapts [`resources/template.html`](resources/template.html), and visually verifies the result before delivery.

## Directory contents

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Agent-facing design rules, layout semantics, workflow, and output contract. |
| `agents/openai.yaml` | Codex display metadata and default prompt. |
| `resources/template.html` | Starting point for the self-contained HTML/SVG deliverable. |
| `LICENSE` | MIT notices retained from the upstream projects. |

## Runtime notes

The HTML opens directly in a modern browser. The diagram itself is inline, while JetBrains Mono, PNG capture, and PDF export load pinned resources from Google Fonts and jsDelivr. Those optional features require network access when the file is opened.

This skill was adapted from [`hstarorg/skills`](https://github.com/hstarorg/skills), which credits Cocoon AI's architecture diagram generator. See [`LICENSE`](LICENSE) and the repository's third-party notices for attribution.
