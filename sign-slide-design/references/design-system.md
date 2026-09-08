# Sign deck design system

This is the complete standalone specification for everyday Sign slide authoring. Apply these semantic tokens and rules directly in PowerPoint, Google Slides, Figma Slides, or another presentation format. Do not fetch an external template before using them.

## Packaged version

- Sign Deck Design System: V1.0 / 08-2026
- Standalone package revision: 2026-09-07
- Included assets: Sign logo, two approved orange section textures, Archivo, IBM Plex Mono, and their license notices

The files in `assets/` and the rules below are sufficient to create and validate a Sign deck offline. External-source identity and update procedures live separately in `source-maintenance.md` and are relevant only when maintaining this skill.

## Canvas and anatomy

- Canvas: 1600 × 900, 16:9.
- Standard side margins: 75 px.
- Header frame: x 63, y 20, width 1474, height 111. Header title begins at x 75.
- Body frame: x 75–1525, y 170–830.
- Footer frame: x 0, y 840, width 1600, height 60.
- Header contains, in order: optional outline tag, slide title, flexible hairline, Sign logo at top right. Logo footprint is approximately 111 × 54 px.
- Footer centers `2026 Sign. All Rights Reserved.` and places the page number at the right edge. Update the year only when the official template does.
- Use 24–32 px gutters; use 24 px vertical spacing for stacked lists.
- Use 8–12 px corner radii. Prefer flat surfaces; optional shadow is black at 8% opacity, y 2, blur 10.

Keep title and section slides minimal. Content slides should respect the header/body/footer zones unless an approved layout explicitly departs from them.

## Color tokens

| Token | Value | Use |
| --- | --- | --- |
| White | `#FFFFFF` | Default slide and card background |
| Primary | `#FF7801` | Emphasis, key rules, small highlights |
| Primary Deep | `#E14603` | Logo gradient, deeper accents |
| Primary BG | `#FFF6EE` | Warm panels and highlighted areas |
| Black | `#1E2228` | Primary text and dark section backgrounds |
| Text Secondary | `#4A5361` | Supporting copy |
| Light Grey | `#F5F5F5` | Neutral panels |
| Medium Grey | `#E4E7EC` | Borders and separators |
| Dark Grey | `#969696` | Quiet metadata and inactive states |

Ordinary content slides are predominantly white and black. Orange is a signal, not wallpaper. Full-bleed orange gradients belong only on title or section slides.

## Typography

Use Archivo for titles, subtitles, body copy, captions, and footer text. Use IBM Plex Mono only for labels, table headers, diagrams, and graphs.

| Role | Family and style | Size | Line height / tracking |
| --- | --- | --- | --- |
| Display title | Archivo Light | 80 px | 98%; -4% |
| Section title | Archivo Light | 60 px | 110% |
| Slide title | Archivo Regular | 34 px | Natural |
| Subtitle | Archivo Light | 28 px | +10% tracking |
| Card heading large | Archivo SemiBold | 40 px | Natural |
| Card heading | Archivo SemiBold | 32 px | Natural |
| Card heading small | Archivo Bold | 28 px | Natural |
| Body large | Archivo Light | 30 px | Natural |
| Body default | Archivo Regular | 20 px | Natural |
| Body small | Archivo Regular | 16 px | Natural |
| Caption | Archivo Regular | 13 px | Natural |
| Footer copyright | Archivo Regular | 18 px | Natural |
| Footer page | Archivo SemiBold | 18 px | Natural |
| Mono label | IBM Plex Mono Regular | 20 px | Uppercase |
| Mono body | IBM Plex Mono Regular | 17 px | Natural |
| Mono small | IBM Plex Mono Regular | 13 px | Natural |

Do not introduce decorative fonts. Avoid heavy bold across whole headlines; use weight contrast sparingly to emphasize one phrase.

## Components and graphics

Approved component families include: Sign logo, content header, content footer, callout, feature card, text card, highlight panel, numbered item, 3-column table, big number, pull quote, roadmap step, agenda item, profile card, outline tag, and accent tag.

Custom diagrams use IBM Plex Mono text, orange-tinted fills on cream, hairline borders, light hatching, and generous whitespace. Prefer simple native shapes and editable connectors. Do not imitate generic SaaS dashboard cards or use unrelated stock icon styles.

## Non-negotiable checks

- The logo is an official asset and retains its proportions.
- Content slides do not become full-orange.
- Body copy remains comfortably readable at presentation distance.
- Orange denotes a meaningful focal point or state.
- Repeated header/footer geometry is consistent.
- The deck uses no more than two font families: Archivo and IBM Plex Mono.
