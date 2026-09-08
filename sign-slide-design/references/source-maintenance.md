# Official source maintenance

Read this file only when the task is to refresh or audit the packaged Sign slide-design skill itself. Ordinary presentation work uses `design-system.md` and the bundled assets without contacting Figma.

## Canonical source

- URL: `https://www.figma.com/design/GLoo96tpJFrXQ6WcQTdDC0/Deck?node-id=6685-200&p=f&m=dev`
- File key: `GLoo96tpJFrXQ6WcQTdDC0`
- Root node: `6685:200`
- Last inspected: 2026-09-07
- Source label at last inspection: V1.0 / 08-2026

Relevant source sections at the last inspection:

- Color: `6685:246`
- Typography: `6685:293`
- Slide anatomy and grid: `6685:327`
- Components: `6685:360`
- Slide templates: `6685:562`
- Example layouts: `6685:750`
- Graphics and illustration: `6685:823`

## Refresh procedure

1. Confirm that the source is the official Sign deck system and record its displayed version.
2. Compare semantic colors, typography roles, slide geometry, repeated header/footer elements, components, layout archetypes, and graphics rules against the packaged references.
3. Update only rules that changed in the official source. Preserve useful presentation judgment that does not conflict with the source.
4. Export changed official assets into `assets/` as stable local files. Never store expiring Figma download URLs.
5. Keep the logo's original paths and proportions. Retain font license notices whenever font assets remain bundled.
6. Update the package revision and source inspection date. Keep the official design-system version separate from the skill package revision.
7. Run the skill validator, search ordinary references for accidental remote dependencies, and create or review a representative deck before publishing the update.

## Maintenance acceptance checks

- `SKILL.md`, `design-system.md`, and `layout-patterns.md` remain sufficient for offline authoring.
- Only this maintenance reference contains Figma identifiers or synchronization instructions.
- All assets referenced by the ordinary workflow exist locally.
- No temporary or authenticated asset URL appears outside maintenance notes.
- A representative title slide, content slide, diagram slide, and closing slide match the updated source at normal presentation scale.
