# Design: first light

**Mode:** Operate, for people who have never built an agent. Every screen does one thing.

**World:** the dark side of a planet at sunrise. One canvas draws a curved horizon with a thin bright rim, a soft sun that slowly breathes, and faint stars. The horizon moves to where it means something: behind the agent core on the creator (the core sits in the sunrise), low behind the message box in a chat, at the bottom of other pages. Almost nothing is boxed: content sits directly on the sky, separated by space and hairlines.

Reference for the motion and type: the cinematic hero, heavy uppercase display and blur-in reveals of rayhanm.com, adapted for an app. No assets are copied; the sky is drawn in code.

## Structure

- **Sidebar** (like a list of conversations): New agent, your agents (orb + name + a dot when one is working or waiting for you), then Approvals, Leaderboard, Library, Team jobs, and the dev identity switcher.
- **Creator** (`#/new`): drag tools onto the core (or click them), say what it should do, pick a model, Create agent. One screen, one button. The tools land in orbit around the core.
- **Agent** (`#/agent/:id`): a chat. You type, it answers. Approvals appear inside the conversation as a question ("I'd like to build a slideshow. Okay to go ahead?") with Go ahead / Change something / Don't. Results (slides, documents, charts, sources) appear inline. Steps and ratings sit quietly under each reply.

## Tokens (`static/style.css`)

| Role | Value |
| --- | --- |
| Void | `#02040a` |
| Ink / dim / faint | `#eef2fb` / `#a2adc4` / `#66728c` |
| Ice (live, light, focus) | `#bfefff` |
| Waiting for a person | `#ffc073` amber |
| Primary button | solid white pill on the dark sky |
| Display | Unbounded, uppercase, for page titles only |
| Body | Hanken Grotesk |

## Motion

- **Focal moment:** headlines blur into focus word by word (1s, 70ms stagger, `cubic-bezier(.16,1,.3,1)`); the rest of the screen rolls in behind them, blurred to sharp.
- **Creator:** the core's halo breathes; while you drag, it speeds up and the ring tightens; a dropped tool lands in orbit (blur, scale up) and the core flashes as it absorbs it.
- **Chat:** "Thinking" shimmers while the agent works; a new agent's orb ignites once.
- **Ambient:** the sun breathes on an 18s cycle, stars twinkle, the horizon glides between positions when you change screens.
- **Budget:** one canvas, paused when the tab is hidden. Reduced motion draws one still frame and removes every animation and blur.
