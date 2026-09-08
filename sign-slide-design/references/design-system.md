# Sign deck design system

Use these tokens for non-Figma presentation formats. In Figma, apply the corresponding variables and text styles instead of raw values.

## Source and freshness

- Canonical source: `https://www.figma.com/design/GLoo96tpJFrXQ6WcQTdDC0/Deck?node-id=6685-200&p=f&m=dev`
- Figma file key: `GLoo96tpJFrXQ6WcQTdDC0`
- Root node: `6685:200`
- Snapshot inspected: 2026-09-07
- Template label shown in source: V1.0 / 08-2026

When the user asks for the latest system, inspect the source page and the relevant template/component nodes. Update this reference only when the official source changed. Export stable local assets; do not copy temporary Figma asset URLs into this skill.

Key sections: color `6685:246`; typography `6685:293`; anatomy/grid `6685:327`; components `6685:360`; templates `6685:562`; example layouts `6685:750`; graphics `6685:823`.

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

Canonical component nodes include: logo `6685:361`, content header `6685:373`, content footer `6685:391`, callout `6685:397`, feature card `6685:400`, text card `6685:406`, highlight panel `6685:477`, numbered item `6685:496`, 3-column table `6685:503`, big number `6685:529`, pull quote `6685:533`, roadmap step `6685:540`, agenda item `6685:545`, profile card `6685:552`, outline tag `6685:558`, and accent tag `6685:560`.

Custom diagrams use IBM Plex Mono text, orange-tinted fills on cream, hairline borders, light hatching, and generous whitespace. Prefer simple native shapes and editable connectors. Do not imitate generic SaaS dashboard cards or use unrelated stock icon styles.

## Non-negotiable checks

- The logo is an official asset and retains its proportions.
- Content slides do not become full-orange.
- Body copy remains comfortably readable at presentation distance.
- Orange denotes a meaningful focal point or state.
- Repeated header/footer geometry is consistent.
- The deck uses no more than two font families: Archivo and IBM Plex Mono.
