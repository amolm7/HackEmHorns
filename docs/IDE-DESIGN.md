> Superseded by the visual workspace redesign. See docs/VISUAL-DESIGN.md.

# Reference analysis and implementation

Reference: https://www.rayhanm.com/ (reviewed October 24, 2026).

## Evidence and limits

The public HTML and stylesheet were inspected. The browser displayed a deep dark teal canvas and sparse icon navigation, but the main animated content did not render during inspection. The source reveals the content hierarchy and motion vocabulary; exact live animation timing and interactions were not visually verified. This implementation interprets that direction for an agent application rather than copying a portfolio.

## Visual analysis

- Typography: reference loads Space Grotesk for headlines and Inter for body copy, with a separate label role. It contrasts large, tightly tracked headings with quiet metadata. Our existing local body font remains readable; system monospace becomes the display and label voice to meet the IDE request without downloading assets.
- Color: the visible canvas is almost black with teal undertones. White content and muted secondary text do the heavy lifting. The adaptation uses charcoal editor surfaces, pale text, mint actions, blue file accents, and amber approval states.
- Composition: sparse navigation, substantial negative space, strong section hierarchy, and a clear distinction between display text and supporting information. The application needs denser controls, so a persistent editor shell provides structure while forms keep generous spacing.
- Motion: source keyframes include character reveals, translated CTA entrances, blurred experience roll-ins, drifting posters, breathing light, and traveling scroll cues. Use brief opacity/translation reveals and a finite cursor introduction. Avoid blocking preloaders or character animation on controls and user-generated content.
- Interaction: adapt file tabs, an explorer rail, editor breadcrumbs, fine borders, and a status bar. Navigation labels remain “Team work”, “Agents”, “Inbox”, and “Library”; users do not need to know code or terminal commands.

## Implementation stages

1. Shell: title bar, navigation tabs, explorer rail, breadcrumbs, and status footer.
2. Components: neutral editor panels, compact corners, monospace hierarchy, accessible fields, selected rows, and clear approval colors.
3. Entry point: a large introductory heading and a small illustrative configuration panel explaining goal → shared skills → review → reuse. The example is explicitly labeled and does not claim to show a saved agent.
4. Motion: remove the continuous globe and card tilt. Add short staged navigation entrances, active-tab underline movement, and a limited cursor blink. Respect reduced motion.
5. Verification: JavaScript parsing, screen-render checks, HTTP/static response checks, and browser review where available. Preserve backend authorization and all existing API contracts.

## Guardrails for usability

The two-step creation flow stays intact. Model settings remain optional. IDE styling must not turn forms into an actual code editor or require commands. Status text is derived from loaded state, not fake connection or deployment indicators. Demo mode remains explicitly identified.
