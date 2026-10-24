# Design: "Mission control"

**Mode:** Operate. People come here to create an agent, give it work and review the result. Expression lives in the details; scanability wins.

**World:** a dark instrument room. Deep blue-black space, frosted glass panels with a thin lit edge, one slowly turning wireframe globe behind everything, and each agent shown as a small glowing orb with an orbit ring. Calm, precise, a little cinematic.

## Tokens (see `static/style.css`)

| Role | Value |
| --- | --- |
| Space | `#05070d` base, `#0a1020` raised |
| Glass | `rgba(16, 24, 44, .62)` with a 1px edge `rgba(160, 190, 255, .14)` |
| Ink | `#e8eefc` / `#a9b6d3` / `#7886a9` |
| Signal (the one accent) | `#4ff0c8` mint |
| Attention | `#ffb454` amber (needs you), `#ff6b81` coral (stop / failed) |
| Display type | Unbounded (variable), used for headings only, never above 2rem |
| Body type | Hanken Grotesk (variable) |

Fonts are self-hosted from `static/fonts` (SIL OFL licences alongside) because the CSP allows only same-origin resources. Monospace is reserved for raw data and code.

## Rules

- One accent. Mint means "go / alive / yours". Amber means "waiting for a human". Nothing else is coloured for decoration.
- Glass is used where it carries depth (panels over the globe). No gradient text, no nested cards, no icon-tile-heading page structure.
- Icons are authored SVG at one stroke weight (`icon()` in `app.js`).
- Depth: the globe, a gentle 3D tilt on pointer hover for cards (fine pointers only), soft offset shadows.

## Motion thesis

- **Focal moment:** a new agent's orb *ignites* once, when you land on its page after creating it (ring sweeps in, glow blooms, 700 ms).
- **Continuity:** screens rise 8 px and fade in (240 ms, exponential ease-out) on navigation only, never on background refreshes. Card grids stagger by 30 ms.
- **Feedback:** buttons press to 0.97; the autonomy switch re-lights its orb ring.
- **Budget:** one canvas, paused when the tab is hidden or the user prefers reduced motion (a still frame is drawn instead). Only `transform` and `opacity` animate.

## Product language

An agent **asks first** (every action needs approval) or **runs alone** (reads and local saves proceed; actions with outside effects still ask). The leaderboard ranks agents by what managers actually did: results they rated as successful, and actions they approved.
