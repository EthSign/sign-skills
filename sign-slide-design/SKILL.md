---
name: sign-slide-design
description: Apply Sign's official presentation design system when creating, redesigning, or reviewing slide decks for Sign. Use for PowerPoint, Google Slides, Figma Slides, or slide storyboards when the request mentions Sign branding, the company deck template, or making slides feel "more Sign"; do not use for ordinary presentations without a Sign brand requirement.
---

# Sign Slide Design

Treat this as a brand and presentation-judgment layer. Use the presentation-authoring skill or connected slide tool for file mechanics.

## Workflow

1. Identify whether the task is deck creation, redesign, or brand review. Preserve the user's copy and factual claims unless rewriting is explicitly in scope.
2. Read [references/design-system.md](references/design-system.md) for every task. Read [references/layout-patterns.md](references/layout-patterns.md) when selecting or changing slide compositions.
3. Establish the audience, desired decision, duration, and one message per slide before styling. For sales and demo decks, build an argument or scenario instead of a feature catalogue.
4. Select an approved archetype from the layout reference. Extend the system only when no archetype can communicate the idea cleanly.
5. Use the exact semantic tokens, canvas, header, body frame, footer, typography roles, spacing, and official assets. Keep normal content slides white or near-white; reserve full-bleed orange for title and section moments.
6. Preflight fonts. Use Archivo for presentation prose and IBM Plex Mono only for labels, tables, graphs, and diagrams. Bundled files in `assets/fonts/` may be registered in a task-local renderer. Do not permanently install fonts without permission or silently substitute them in the final deliverable.
7. If the user explicitly requests the latest template or supplies a newer Figma source, refresh only the relevant official nodes before authoring and update the snapshot date in the reference. Otherwise, use the documented snapshot.
8. Render every finished slide and inspect both individual slides and the full-deck sequence. Fix clipping, weak hierarchy, inconsistent repeated elements, arbitrary orange usage, and deviations from the supplied design. Report any intentional deviation.

## Asset Rules

- Reuse `assets/sign-logo.svg`; never redraw, recolor, crop, stretch, or place it on a background that compromises legibility.
- `assets/section-texture-*.svg` are optional title/section decoration. Keep text editable and maintain strong contrast.
- Font assets are provided for faithful task-local rendering. Preserve their license files when copying or distributing the skill.
- Never store or reference expiring Figma asset URLs in a deliverable.

## Source Priority

Apply sources in this order: explicit user constraints, current supplied Sign template, documented Sign design-system snapshot, then general presentation conventions. If a supplied template materially differs from the snapshot, surface the conflict instead of blending the two silently.
