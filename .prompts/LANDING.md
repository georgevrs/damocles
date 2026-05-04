# DAMOCLES — Landing Page Build Prompt

You are tasked with building a **marketing / pitch landing page** for Damocles, the sovereign intelligence-analysis platform built for the EYP (Greek National Intelligence Service) National Security Innovation Challenge 2026. This page is what the panel sees the night before the pitch when they Google "Damocles". It is the *cold open* — it must make a senior intelligence officer want to scroll, then book the demo.

This is a one-shot prompt: read it, build the page, do not ask follow-up questions.

---

## 0. CONTEXT — What Damocles is

You do not need to read the full codebase. Here is the brief:

- **Damocles** is a sovereign intelligence-analysis platform. It fuses four free public data sources — Sentinel-1 SAR satellite radar, AISStream maritime traffic, GDELT 2.0 global news events, Telegram public-channel signals — into a Neo4j knowledge graph + a DuckDB fact store, then pushes that through five LLM agents (Geospatial, OSINT, Linguist, Devil's Advocate, Supervisor) to produce a cited intelligence brief.
- The **gold-medal differentiator**: every sentence in every brief traces to a source node in the knowledge graph. Click a sentence → the map flies to the source coordinates, the graph highlights the cited node, the raw evidence (SAR tile / news article / Telegram message) opens. No competitor has this.
- **Sovereignty** is the pitch. LLM provider abstraction lets us run on Google Gemini for development and switch to a local Ollama model with zero code changes. Zero data leaves Greek infrastructure in production.
- **Audit chain**: every model call, every analyst action, hashed and Merkle-chained across two stores (Neo4j + JSONL). Any parliamentary committee can verify the log has not been tampered with.
- **Three weeks, Greek team, free public data, €1,500 of hardware.** Palantir costs €3M per deployment, requires a US cloud, cannot run in Greek. Damocles costs zero to run.
- **Phase 2 capabilities**: daily Greece-wide standing scan persisting to a DuckDB cache (no per-watch re-fetch), AI-inferred Areas of Interest (HDBSCAN + alpha-shape + LLM naming in Greek), analyst-drawn polygon overlays (terra-draw), WebGL knowledge graph (Sigma.js, scales to 10k+ nodes), rich layered map (vessel trajectories, semantic icons, satellite basemap toggle, news density heatmap).

If you want more detail, `.prompts/PLAN.md` has the full build doc and `docs/demo-script.md` has the 5-minute pitch. **Do not** simply paraphrase those documents; lift specific phrases (see §6).

---

## 1. DELIVERABLE

Create a new Vite project at `landing/` (sibling of `frontend/`). It must be a **separate, self-contained, statically-deployable** project so it can be hosted anywhere (Greek-hosted CDN, GitHub Pages, an EYP-controlled bucket) without depending on the operational backend.

```
landing/
├── package.json
├── vite.config.ts
├── tailwind.config.ts
├── postcss.config.js
├── index.html
├── tsconfig.json
├── public/
│   └── (any static assets you create — favicons, OG image, etc.)
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── index.css
    ├── sections/        (one component per page section — see §3)
    ├── components/      (reusable: Button, GlowCard, AnimatedCounter, etc.)
    └── lib/             (animation hooks, intersection-observer wrappers, etc.)
```

`npm install && npm run dev` must launch the page at `http://localhost:5174` (use port 5174 so it doesn't collide with the operational frontend on 5173). `npm run build` must produce a deployable `landing/dist/`.

---

## 2. TECH STACK — locked in

- **React 18 + TypeScript + Vite 5** — same versions as `frontend/`.
- **Tailwind CSS 3** — utility-first; **do not** install a UI kit (no shadcn, no MUI, no Chakra). Custom components only.
- **Framer Motion** (`framer-motion`) — for scroll-driven animation, page transitions, layout animations. This is the primary animation engine.
- **Lucide React** — same icon set as the operational frontend, for visual consistency.
- **MapLibre GL** (optional) — if you build the hero animation as a styled MapLibre canvas (see §4 — strongly preferred). MIT-licensed BSD-3 fork.
- **`react-intersection-observer`** — for scroll-driven section reveals.
- **NO** stock images. **NO** Lottie files. **NO** placeholder gradients pulled from CDN. All visuals are either CSS, SVG, or canvas/WebGL drawn in the page.
- **NO** Greek public data fetching at runtime. The page is fully static.

Do not install anything else without a clear reason.

---

## 3. PAGE STRUCTURE — what to build

The page is **one long scroll**, not a multi-route site. Sections in order:

### §3.1 — Hero (`sections/Hero.tsx`)
- Full viewport (`h-screen`).
- Top-left: a small monogram — a **rotated amber square**, the same `bg-threat-amber rotate-45` shape used in the operational topbar. Next to it: `DAMOCLES` in tracking-wide monospace + a small build-version chip (`v1.2 · phase 2`).
- Top-right: small links — `Capabilities · Architecture · Demo · Contact`. Smooth-scroll anchors.
- Centre: a giant headline. Two lines:
  - `Cited intelligence,` (regular weight)
  - `at the speed of the threat.` (italic serif)
  Use a serif display font (system serif `Georgia, "EB Garamond", serif` is fine — do **not** import a webfont unless you also vendor it locally).
- Below the headline: a 1-sentence subhead in muted slate: `Sovereign analysis platform fusing SAR, AIS, GDELT and Telegram into a Merkle-chained knowledge graph. Built in Greek, in three weeks, for €1,500.`
- Two CTAs side-by-side: `Watch the demo →` (amber primary), `Read the architecture` (ghost). Hover micro-animation on both.
- **Background**: a live, animated WebGL map of the Aegean as a hero canvas. See §4.1. The map is dark, slowly panning, and **vessel-track lines fade in and trail across the sea** at 2-3x sped-up time. Cited points pulse amber. The hero text sits above the map with a darkening gradient overlay so the text remains readable.
- A subtle scroll cue at the bottom (animated chevron) that gently bounces.

### §3.2 — The Problem (`sections/Problem.tsx`)
- A "stat strip" — three counters that animate from 0 to their final value when the section enters view:
  - `14,000` — *signals waiting in an analyst's queue today*
  - `47` — *that they will review by end of shift*
  - `0.34%` — *the coverage rate*
- Below the strip, two short paragraphs:
  - "Intelligence today is a triage problem disguised as an information problem."
  - "Damocles changes that number — by routing every signal through a transparent agent layer that surfaces only what is corroborated, cited, and challenged."
- Use `framer-motion`'s `useInView` to animate the counters and stagger-fade the paragraphs.

### §3.3 — The Citation Chain (`sections/CitationChain.tsx`) — *the gold-medal section*
- A two-column layout. Left: a stylised "brief" panel — a fake BLUF sentence with one word underlined in amber. Right: a stylised map + graph strip.
- On scroll-into-view, run a **scripted choreography**:
  1. The underlined word in the brief gets a subtle pulse.
  2. A line draws from the word to a coordinate pin on the map (use SVG `<path>` with `pathLength` animation).
  3. The map pin pulses amber.
  4. A cluster of three nodes in the graph strip light up in sequence and a faint "CITES" edge animates between them.
  5. A small evidence card slides up from the bottom showing a fake SAR tile preview (you can synthesise this with a CSS-only noisy radial gradient + a bounding rectangle overlay — do **not** use a real image).
- On the right: a kicker — `One click. Three sources. Zero hallucinations.`
- Below the choreography: small body copy explaining the citation chain in two sentences.
- **This section is the page's centrepiece.** It must look expensive. Slow it down — total animation duration ~3.5 seconds. Use `motion.path` with `pathLength: [0, 1]` and `transition: { duration: 1.2, ease: "easeInOut" }`.

### §3.4 — The Pipeline (`sections/Pipeline.tsx`)
- A horizontal timeline. Five stages, each a card:
  1. **Sense** — Sentinel-1 SAR · AIS · GDELT · Telegram
  2. **Fuse** — Spatiotemporal correlation, threat-grade rules
  3. **Reason** — 5 LLM agents in parallel
  4. **Challenge** — Devil's Advocate adversarial review
  5. **Sign** — Merkle-chained audit log
- On scroll, the cards fade in one at a time. A connecting line draws between them as each appears (SVG path animation).
- Each card has an icon (Lucide), a short title, and 2-3 lines of body. Hover lifts the card with a subtle amber glow.

### §3.5 — Phase 2 Capabilities (`sections/Capabilities.tsx`)
- A 2x3 grid of "feature" cards. Each card: an icon, title, body (2-3 lines), and a tiny visual element specific to it:
  1. **Greece-wide standing coverage** — daily 7-day scan, persistent fact store. Visual: a tiny pulsing map of Greece (SVG silhouette).
  2. **AI-defined Areas of Interest** — HDBSCAN + alpha-shape + Greek naming. Visual: an animated polygon morphing from points to shape.
  3. **Analyst-drawn polygons** — terra-draw on MapLibre. Visual: a cursor "drawing" a small dashed polygon.
  4. **WebGL knowledge graph** — Sigma.js, 10k+ nodes. Visual: a few force-directed dots wiggling.
  5. **Rich map layers** — trajectories, satellite basemap, semantic icons, news heatmap. Visual: stacked layer cards with a parallax effect on hover.
  6. **Tamper-evident audit chain** — Merkle structure, two stores, parliament-grade. Visual: a tiny chain of hash-prefixed blocks animating.
- Cards are subtly different sizes (one `col-span-2`) to break the grid monotony.

### §3.6 — The Numbers (`sections/Numbers.tsx`)
- Six big numbers in a wide horizontal strip with labels:
  - `€0` — to run
  - `€1,500` — total hardware
  - `3 weeks` — build time
  - `0` — Greek bytes leaving Greek infrastructure (production)
  - `5` — agents in the reasoning layer
  - `41` — audit-chain entries verified pre-pitch
- Each number animates in (CountUp from 0) when in view, with a faint amber underline drawing beneath.
- Below the strip: a single italic line — `These are the numbers we can't change. They are also the numbers Palantir cannot match.`

### §3.7 — How the demo lands (`sections/Demo.tsx`)
- A vertically-stacked re-creation of the 5-minute demo script. Each timestamp `[0:00]`, `[0:30]`, `[1:30]`, `[2:00]`, `[3:00]`, `[3:30]`, `[4:45]` is a row.
- Left column: timestamp + a one-sentence script line (paraphrased from `docs/demo-script.md`).
- Right column: a tiny visual cue (icon + caption) of what the panel sees at that moment.
- On scroll, rows reveal in sequence and a vertical timeline line draws down on the left.

### §3.8 — Architecture in one diagram (`sections/Architecture.tsx`)
- A single SVG block diagram. Three columns: **Sense** (4 sensor blocks), **Fuse + Reason** (DuckDB + Neo4j + 5 agent blocks + Merkle log), **Surface** (Brief + Map + Graph + Audit panels).
- Animated dotted lines between blocks indicate dataflow. Lines have a moving dash pattern (CSS `stroke-dashoffset` animation) so they look "live".
- Caption: `Every block runs on free, public, sovereign components. Every connection is auditable.`

### §3.9 — The pitch (`sections/Close.tsx`)
- Centre-aligned. A single big sentence in a serif font:
  > *"The question for EYP is not whether they can afford Damocles. It is whether they can afford not to have it."*
- Beneath, a button: `Book the demo · 5 minutes`.
- Beneath that, three small inline links: `GitHub · docs.damocles.gr (placeholder) · contact@damocles.gr (placeholder)`.

### §3.10 — Footer (`sections/Footer.tsx`)
- Minimal. Build date (today), platform sovereignty stamp, license, EYP ICN 2026 reference.
- Tiny `Σ` (sigma — for Sovereignty) glyph as a closing flourish.

---

## 4. ANIMATION BAR — non-negotiable specifics

Animation is what separates this from a generic SaaS landing page. The page must feel like an instrument, not a brochure.

### §4.1 — Hero map canvas
- Use `maplibre-gl` directly (no react-map-gl wrapper needed for a static decorative map).
- Style: CARTO Dark Matter (`https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json`).
- Centred on the Aegean (lon 25.5, lat 37.5, zoom 5.6).
- Disable user interaction (`interactive: false`) so it doesn't fight the scroll.
- On mount, run a slow continuous pan: a `setInterval` that bumps `bearing` by 0.05° / 200ms, giving a barely-perceptible drift.
- Render **decorative vessel trails** as a `LineString` source. Generate 8-15 synthetic trails (random starts, plausible Aegean routes — Lemnos→Lesvos→Chios, Athens→Crete, Rhodes→Karpathos, etc.) and animate `line-gradient` along each so a glowing dot appears to traverse the line. Repeat in a loop.
- Render 3-4 `circle` markers at fake "incident" coordinates with a CSS-driven pulse ring above them (concentric circles expanding from radius 0 to 30px with opacity fading — re-use the pattern in `frontend/src/components/MapPanel.tsx` lines 88-108).
- Place a darkening linear gradient `<div>` over the canvas so the hero text remains readable.

### §4.2 — Scroll-driven reveals
- Every section uses `react-intersection-observer` + `framer-motion`'s `useAnimation` to fire a reveal when 30% of the section enters the viewport. Reveals are: opacity 0→1, y-translate 24px→0, staggered children at 80ms.
- **Once revealed, do not re-animate on scroll-back.** Use `triggerOnce: true` on the observer.

### §4.3 — Specific animations to implement
- **Counter animation** (Problem, Numbers sections): write a `<AnimatedCounter target={14000} duration={1.4} />` component. Use `requestAnimationFrame` with `easeOutQuart`. Format thousands with a thin space (`14 000` style — Greek numeric convention).
- **Path-draw** (Citation Chain, Pipeline, Architecture sections): SVG paths with `strokeDasharray={length} strokeDashoffset={length}` animating to `0`. Wrap in `motion.path` so we can set `whileInView`.
- **Glow on hover** (Capabilities cards): `box-shadow: 0 0 32px -8px rgba(245, 158, 11, 0.4)` transitioning over 240ms.
- **Cursor parallax** on the hero text: subtle (max ±6px) translation based on `useMotionValue` hooked to mousemove. Only triggers when the cursor is over the hero.
- **Magnetic CTA buttons**: when the cursor approaches within 80px, the button gently translates toward the cursor (max ±8px). Returns smoothly on leave.
- **Text-reveal headline** (Hero): the headline letters appear left-to-right with a 30ms stagger. Each letter starts with `opacity: 0, y: 20, filter: blur(4px)` and animates to baseline. Use `motion.span` per word, not per letter, to avoid an absurd number of motion components.
- **Sticky scroll-progress bar** at the very top of the viewport — a 2px amber bar that fills horizontally as the page scrolls. Uses `useScroll` + `useTransform` from framer-motion.

### §4.4 — Performance budget
- Keep the hero canvas frame rate ≥ 50 FPS on a mid-range laptop. If it drops, reduce the number of vessel trails, not the visual quality of each.
- The page must be ≤ 600KB of JS gzipped (excluding MapLibre, which is allowed to bring its own bundle). Run `npm run build` and check.
- Lazy-load below-the-fold sections via `React.lazy` if needed.

---

## 5. VISUAL LANGUAGE — colour, type, spacing

### Palette (Tailwind config, custom colours)

```ts
// tailwind.config.ts
extend: {
  colors: {
    "panel-bg":      "#0b0f17",   // deep aegean night — page background
    "panel-surface": "#111827",   // raised cards
    "panel-border":  "#1c2433",
    "panel-text":    "#e2e8f0",
    "panel-muted":   "#94a3b8",
    "threat-amber":  "#f59e0b",   // primary accent (brief BLUF, AI AoIs)
    "threat-red":    "#ef4444",
    "audit-emerald": "#10b981",   // OK / verified
    "data-cyan":     "#22d3ee",   // user-drawn AoIs, broadcasting vessels
    "linguist-fuchsia": "#e879f9",
  },
  fontFamily: {
    serif: ['Georgia', '"EB Garamond"', 'serif'],
    sans:  ['"Inter"', 'system-ui', 'sans-serif'],
    mono:  ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
  },
}
```

(You may swap to system-default font stacks if you don't want to ship webfonts. **Self-host any webfont you do use** — do not pull from Google Fonts; sovereignty.)

### Typography rules
- Headlines: serif, large (clamp 48-96px), **italic** for the second clause of a two-clause headline.
- Body: sans, 16px, line-height 1.6, max-width 65ch.
- Stats / data / version chips / timestamps: monospace, slightly tighter tracking.
- Section titles: monospace, uppercase, tracking-widest, small (12-14px) — so they read like "labels" not titles.

### Spacing
- Generous. Sections are ≥ 120px tall vertical padding. The page should breathe.
- Use Tailwind's `container` with `max-w-6xl mx-auto px-6` for content blocks. Hero is full-bleed.

### Imagery
- **No photographs.** Visual identity is: dark background + amber accent + a few glowing thin lines + monospaced data text.
- Sword-of-Damocles imagery: do **not** make it literal. The motif is abstract — a small rotated square hanging by a thread, used once in the hero monogram and once in the footer. Resist the temptation to draw an actual sword.

---

## 6. COPY — actual text to use

Lift these phrases verbatim. They are the demo's load-bearing language and have been pressure-tested:

- *"Cited intelligence, at the speed of the threat."*
- *"Sovereign analysis platform fusing SAR, AIS, GDELT and Telegram into a Merkle-chained knowledge graph."*
- *"Three weeks. Greek team. Free, public data."*
- *"One click. Three sources. Zero hallucinations."*
- *"Damocles institutionalizes skepticism."*
- *"On the chain. Always."* (audit chain)
- *"Not a summary of a summary. A citation chain — the same standard you would expect in a court."*
- *"The question for EYP is not whether they can afford Damocles. It is whether they can afford not to have it."*

Avoid these phrases (they are listed in `docs/demo-script.md` §"Phrases to avoid" — engineering-audience hostile):
- "AI" without qualification
- "Powered by"
- "Cutting edge", "state of the art", "best in class"
- "Disrupt", "revolutionize", "transform"
- Any superlative without a number behind it

The tone is: **groundedness over loudness**. Authority comes from specifics. Numbers, names of sensors, the word "sovereign", the word "cited". Never marketing-speak.

---

## 7. ACCEPTANCE CRITERIA

The build is done when:

1. `cd landing && npm install && npm run dev` opens at `http://localhost:5174` without errors.
2. `npm run build` completes with no TypeScript errors and no warnings other than chunk-size for MapLibre.
3. All ten sections (§3.1–§3.10) are present in the order listed.
4. The hero map renders with at least 8 animated vessel trails and 3 pulsing incident markers.
5. Scrolling triggers reveal animations on every section, each only once.
6. The Citation Chain section's choreography runs end-to-end on first scroll-into-view, taking ~3.5s.
7. All CTAs work (smooth-scroll for the in-page anchors; the demo button can be a `mailto:` placeholder).
8. The page is responsive: at 1280px, 1024px, and 768px viewport widths, no horizontal scroll, no text overflow, hero remains legible. Mobile (<768px) can be a polished simplified version — no need for the hero map at all on mobile (replace with a still SVG).
9. Lighthouse Performance score ≥ 85 on a desktop simulation.
10. All copy lifted from §6 appears verbatim somewhere on the page.
11. Zero stock images, zero placeholder text ("lorem"), zero `console.log` noise in production.
12. Append a one-line entry to `docs/limitations.md` if any of these criteria had to be relaxed, explaining why.

---

## 8. WHAT NOT TO DO

- Do not couple the landing page to the operational backend. It is statically deployable.
- Do not add dependencies beyond §2's stack without a written reason.
- Do not write README files for the landing page. The code is the documentation.
- Do not add a "Subscribe to our newsletter" section. This is a national security platform; it does not have a newsletter.
- Do not use emoji anywhere — in copy, in code comments, in icons. Lucide icons only.
- Do not add chatbot widgets, cookie consent banners, or analytics SDKs. The page is sovereign.
- Do not put the Damocles logo as a sword. It is a rotated square. That's the brand.
- Do not "optimise" by skipping the animations. The animations are the product demo.

---

## 9. WHEN YOU'RE DONE

Write a one-paragraph summary of what you built — sections delivered, libraries used, performance numbers, anything you compromised on. Append it to `docs/limitations.md` under a new heading `## Phase 2 — Landing page (date)`. Do not create a new markdown file for it.

Then stop. Do not rebuild the operational frontend. Do not edit `frontend/`. Do not push to git. The user will inspect.

---

*Build document version: landing-1.0*
*Target: EYP National Security Innovation Challenge 2026*
*Aesthetic: instrument, not brochure. Dark, technical, sovereign, expensive.*
*Cold-open standard: a senior intelligence officer who lands on this page at 11pm should book the demo before they close the tab.*
