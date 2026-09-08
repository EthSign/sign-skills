# Sign Slide Design

Apply Sign's official visual system when creating, redesigning, or reviewing presentation decks.

## When to use it

Use this skill when a PowerPoint, Google Slides, Figma Slides, or slide storyboard must follow Sign branding or should feel “more Sign.” Ordinary presentation work without a Sign brand requirement should use the environment's general presentation tooling instead.

The skill supplies the brand and design judgment layer: approved color and typography roles, layout archetypes, spacing rules, official assets, and a visual QA checklist. The active presentation tool remains responsible for editing and exporting the deck.

## Use from Codex

```text
Use $sign-slide-design to redesign this customer deck in Sign's official presentation style.
```

Codex follows [`SKILL.md`](SKILL.md), reads the packaged design system, preserves the user's factual content unless rewriting is requested, and renders every finished slide for inspection.

## Directory contents

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Agent-facing workflow, asset rules, and source priority. |
| `agents/openai.yaml` | Codex display metadata, brand color, icon paths, and default prompt. |
| `references/design-system.md` | Required design tokens and presentation rules. |
| `references/layout-patterns.md` | Approved composition archetypes. |
| `references/source-maintenance.md` | Refresh procedure for maintainers updating the packaged source. |
| `assets/` | Official Sign logo, section textures, fonts, and font licenses. |

## Runtime notes

Ordinary deck work is self-contained and does not require Figma or network access. Archivo is used for presentation prose and IBM Plex Mono for labels, tables, graphs, and diagrams; both are bundled for task-local rendering.

Do not replace the packaged design system during ordinary deck creation. If a newer official template is supplied for a specific deck, follow it for that deck and report the version difference.
