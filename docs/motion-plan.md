# sooth.bet Motion System — Synthesis Plan
## "Witnessed Change" spine (Plan A) + instrument-physics grafts (C) + execution discipline (B)

**Thesis.** Every animation is a receipt for something real: a payload the client just diffed, an action the user just took, or a clock event that just fired. Because board.json refreshes ~30 min, the system is bimodal: **user-action motion** (FLIP sort, row expand, rail slide, crossfades) runs Vercel-instant (120–250ms) and is felt every session; the **rare witnessed refresh** gets the full deliberate choreography (flash-decay + digit roll + pin glide + fair-post breath, ≤1.2s total). Changes that happened while the user was away get static provenance text, never motion. The whole discipline is one line of code: **motion helpers only fire from a diff of previously-rendered state — `prev === null` never animates.** Document this as a contract comment at the top of desk.js.

**Explicit rejections** (protect these in review): no desk power-on load choreography beyond the single land() fade (the "no loading animations everywhere" ban); no pin glide on sport switch (different games = no continuity to animate — crossfade is the honest lens-change); no pointer-parallax deck hover (banned decorative parallax); no timeline path morphs; no per-row stagger cascades on snapshot data; no count-up-from-zero on load; no View Transitions API (unsupported on the dev machine's macOS 12 Safari; FLIP + crossfade cover every case with one code path).

---

## 0. Motion token block — desk.css `:root` (ships first)

```css
/* MOTION CONTRACT: no literal ms values below this block anywhere in desk.css.
   Motion fires only from (a) user action, (b) witnessed payload diff, (c) real clock. */
--t-press: 0ms;          /* :active compress — instant in */
--t-hover: 120ms;        /* hover color/bg/border/filter, plain ease */
--t-view: 150ms;         /* crossfades, tab/lens switches, land() fades */
--t-ui: 200ms;           /* expand, underline slide, default when unsure */
--t-flip: 250ms;         /* FLIP row reorder */
--t-roll: 450ms;         /* digit tick-roll */
--t-flash-hold: 400ms;   /* flash-decay hold */
--t-flash-fade: 1600ms;  /* flash-decay fade to transparent */
--t-draw: 400ms;         /* one-shot SVG timeline draw */
--t-ceremony: 600ms;     /* pick reveal, seal settle, pin glide */
--e-out: cubic-bezier(0.165, 0.84, 0.44, 1);      /* quart-out: everything entering */
--e-inout: cubic-bezier(0.645, 0.045, 0.355, 1);  /* on-screen morphs, crossfades */
--e-glide: var(--e-out);                           /* fallback first (pre-2023 Safari) */
--e-glide: linear(0, 0.009, 0.035 2.1%, 0.141 4.4%, 0.723 12.9%, 0.938 16.7%,
                  1.017, 1.026 20.4%, 1.021 24.3%, 1.006 32%, 0.999 43.1%, 1);
                  /* bounce-free spring, ≤2% overshoot (from C) — instrument settle only,
                     never on numbers; numbers always get --e-out */
```
Rules (comments in the block): exits run ~20% faster than entries; hover = plain `ease`; springs never on numbers; zero bounce anywhere — this is a data instrument.

---

## Ordered build list

### 1. Micro-interaction unification sweep (user action / hover)
- **Trigger:** hover, press, small UI state flips.
- **Technique:** all seven audited instant-snap states — nav links, sport pills (desk.css:100,113), table row hover (:252), `.bp-r` (props.html:39), `an-chip` (:310), `seal-badge` (:407), `.go`/`.hd-cta` (:104; subscribe.html:41) — get `transition: background var(--t-hover), color var(--t-hover), border-color var(--t-hover), filter var(--t-hover) ease`. Press: `:active` compresses `translateY(1px)` instantly, release eases back 150ms (B's instant-in/eased-out detail; keep translateY, not scale — no toy physics). Checkout overlay (subscribe.html:151–189): class-based 150ms opacity fade replacing the `hidden`-attr pop (set `hidden` after exit fade for a11y). `proBadge` flip (desk.js:394–400): 200ms crossfade on stable child spans. crest.js `hydrate()`: img opacity 0 → 1 over 150ms on load. Fix subscribe.html:69's always-on decorative pulse — wire to feedState like every other page or delete it.
- **Files:** desk.css, subscribe.html, desk.js, crest.js. ~25 lines CSS, no new timers.

### 2. `Desk.land()` shimmer→content handoff (request resolution)
- **Trigger:** every load resolution (all three plans converged on this — it fixes the worst first impression sitewide).
- **Technique:** `Desk.land(el, html)` in desk.js near `connecting()` (:126–131): fade `.state`/shimmer to opacity 0 over `--t-view`, swap innerHTML, fade new content root in over `--t-view` `--e-out`. Content appears **whole, one unit, no stagger** — the JSON arrived as one file; animating assembly would lie about the transport. Apply at index.html:282, game.html:230, props/edges/research equivalents. Also fix the desk.js:104–107 `mount()` header pop: reserve header height with `min-height` on the shell so `insertAdjacentHTML` stops causing first-paint layout shift (B's fix), header fades in `--t-view`.
- **Files:** desk.js (~10 lines), desk.css, all page boot blocks.

### 3. Sport rail slide + board crossfade (user lens change)
- **Trigger:** sport pill click.
- **Technique:** fix desk.js:94–100 `sportRail()` — build pills **once**, toggle `aria-selected`/textContent per pill (kills the per-click innerHTML rebuild, also lets per-pill dots update in place). One absolutely-positioned `.rail-ink` underline FLIPs to the active pill: translateX/scaleX over `--t-ui` `--e-out`. The board behind it (`#radar`/`#games`) does a 150ms two-layer opacity crossfade — a sport switch is a lens change, not new data; **no pin glide here** (C's version rejected: different games have no positional continuity).
- **Files:** desk.js (~15 lines), desk.css (~6 lines), index.html.

### 4. Live countdown on /picks (real clock)
- **Trigger:** the seal clock — the only truly live datum.
- **Technique:** upgrade `countdown()` (picks.html:109–115) from render-once to a 1s interval writing `tabular-nums` digit spans (plain text ticks — the only continuously moving element allowed on any page). Amber color transition 300ms only under 5 minutes (a real threshold). This is the only timer added besides the existing 15s heartbeat.
- **Files:** picks.html.

### 5. Row expand/collapse without tbody rebuild (user action)
- **Trigger:** OPEN toggle on picks.html; report rows on research.html.
- **Technique:** replaces the picks.html:215–236 whole-tbody rebuild — insert/remove the **single** detail `<tr>`; animate an inner wrapper `grid-template-rows: 0fr → 1fr` over `--t-ui` `--e-out` (sanctioned one-shot layout animation, user-initiated, off the hot path); content fades in 120ms after. Collapse: ~170ms reverse then remove. Same targeted-insertion fix for research.html:240–255 `render()` — which also stops it destroying in-flight `#ans-<id>` analyzer answers (bug fix, not just polish). Kills the audited scroll-jank.
- **Files:** picks.html (~40 lines), research.html.

### 6. Keyed rows + FLIP sort / non-destructive filter (user action)
- **Trigger:** sort click, search/filter keystrokes on research.html and props.html.
- **Technique:** stop rebuilding tbody (fixes props.html:263 per-keystroke rebuild and research.html:240–255). Build rows once into a Map keyed by event/player id. Sort = reorder DOM via a ~20-line `flip()` helper in desk.js (read rects → mutate → WAAPI translate back-to-zero, `--t-flip` `--e-out`). Filter/search = toggle `[hidden]` with 120ms opacity, plus a 150ms input debounce (B). Budget guard: >40 rows changing → skip FLIP, hard-swap (C).
- **Files:** desk.js (flip helper), props.html, research.html.

### 7. Witnessed-change engine — `Desk.diffPatch()` (the brand centerpiece)
- **Trigger:** a background refetch returns a payload differing from rendered state while the page is open. **Never on load, never on hydration** — `prev === null` guard is the contract.
- **Technique:** piggyback on the existing 15s `Desk.tick` heartbeat (desk.js:409–414): every 20th tick (~5 min) refetch board.json comparing `generated_at` (content timestamp, never mtime; cheap 304s with ETag). Requires stable `[data-cell]` child spans — targeted-update versions of `renderStatus`/`renderGames`/props best-price cells (fixes index.html:110, 196–199 and props.html:185 wholesale innerHTML). Never auto-reorder rows under the reader; if the user is mid-interaction, show a quiet "New data — refresh" banner instead of swapping.
- **Per changed cell — flash-decay + tick-roll:** WAAPI background tint at ~35% alpha (green = improved for bettor, red = worsened, accent = non-directional), `--t-flash-hold` then `--t-flash-fade` to transparent; simultaneously a masked digit roll (`Desk.roll(el, newText, dir)`, ~25 lines: old value translates out in sign direction, new in, `--t-roll` `--e-out`, `overflow:hidden line-height:1` wrapper, `font-variant-numeric: tabular-nums` on `.num`). A **persistent delta glyph** ("+4c · 2m ago") is written alongside — motion accompanies the fact, never carries it. Cap: >20 changed cells → flash none, let the status strip announce (a whole-board change is a new snapshot, not 20 events).
- **Status strip announce:** header chip expands ~250ms `--e-out` to "UPDATED 2:31 PM — 3 MOVES", holds 4s, collapses 200ms; the dot fires ONE ring pulse (scale 1→1.3→1, 700ms, one-shot — distinct from the existing gated 2.4s ambient pulse, which stays exactly as-is as the one permitted loop).
- **Files:** desk.js (diffPatch, roll, ~60 lines), index.html, props.html, edges.html (:149–162 movement rows get data-cell spans).

### 8. Spectrum pin glide + fair-post breath (witnessed refresh; graft from C)
- **Trigger:** same witnessed diff, on /game and expanded picks rows — the same instrument absorbing new data (honest continuity, unlike sport switch).
- **Technique:** refactor `Desk.spectrum()` (desk.js:138–243) to build the SVG skeleton once with stable `data-book` ids per pin `<g>` and a persistent fair-post `<g>`; new `Desk.spectrumUpdate(el, rows)` animates each surviving pin's transform to its new x over `--t-ceremony` `--e-glide`, then commits the attribute; the g-best glow transfers by class toggle after the glide lands. The fair post does one **breath** (stroke-width 2→3.5→2 + glow opacity, 900ms one-shot) — it breathes when it inhales new data, never idles. Range caption "X PTS BETWEEN BEST AND WORST" tick-rolls its scalar. Fixes the index.html:143–161 `renderRadar` wholesale rebuild (sport switch still crossfades).
- **Files:** desk.js, index.html, game.html, picks.html.

### 9. Timeline draw-on + mark pop (one-shot; honest because x IS time)
- **Trigger:** first paint of MARKET TIMELINE on /game only.
- **Technique:** `pathLength="1"` on consensus/book paths (desk.js:272–273, 299–303), stroke-dashoffset 1→0 over `--t-draw` `--e-out`, consensus first, books 80ms behind; `data-drawn` flag + sessionStorage per event id prevents replay. Detected-move marks (:305–312) pop scale 0.5→1 over 200ms — on first draw delayed to their time-fraction, and thereafter ONLY when a mark is new in a witnessed diff. **6H/24H/72H toggle (game.html:199–205): two-layer SVG crossfade 150ms** — render new window off-DOM at opacity 0, crossfade, remove old (C's technique; solves the drawTl innerHTML blocker; no redraw theater, no morphs — the data windows have no continuity to claim).
- **Files:** desk.js, game.html, desk.css (@keyframes draw).

### 10. Analyzer two-beat landing (user-initiated computation)
- **Trigger:** ANALYZE click, then /api/ask resolution.
- **Beat 1 (instant):** deterministic `eventCard` readout pops NOW — scale(0.98)→1 + opacity, 150ms `--e-out` (that speed IS the brand).
- **Beat 2 (async):** `note()` (index.html:257–267, game.html:216, research.html:285) lands via `Desk.land()` into a stable `.an-out` child; numeric spans marked `data-tick` count up ONCE over 450ms rAF ease-out-quart **from the rendered readout values, never from zero**; `Intl.NumberFormat` constructed once outside the frame loop; `tabular-nums` so digits never jitter. The `.an-out` drawer (desk.css:311–314) swaps `:empty` display-toggle for `grid-template-rows 0fr→1fr` 220ms so it unfolds instead of popping. 429-capped branch: fade only, no count-up (B). `data-played` flag: never replays on scroll, tab return, or re-render.
- **Files:** desk.js (`tickTo()` ~12 lines), desk.css, index.html, game.html, research.html.

### 11. Seal→open kickoff ceremony on /picks (real clock event; the payoff)
- **Trigger:** countdown hits zero.
- **Technique:** refetch /api/picks with 10s/30s/60s backoff (B — handles the unlock-flip race; test against a stale-cache response). Label crossfades to "OPEN TO EVERYONE" (180ms). On the unlocked payload: masked ▓▓ rows unmask — blur 4–6px→0 + opacity crossfade over `--t-ceremony` `--e-inout`, light 60ms per-row stagger permitted **here and only here** (a scheduled clock ceremony is an allowed one-shot); the ⛓ SEALED badge settles once (scale 1.03→1 + brightness, 350ms `--e-glide`). No confetti, no post-ceremony loops. sessionStorage guard keyed `revealed-<week-id>` (never a global flag, or week 2 never plays); a reload after kickoff renders the static open view with zero motion — a replayed reveal is a re-enactment.
- **Files:** picks.html (~60 lines), desk.css (~12 lines).

---

## Reduced-motion policy

- The existing global kill at desk.css:65–66 already zeroes all CSS tokens; keep it untouched.
- **JS animations additionally check `matchMedia('(prefers-reduced-motion: reduce)')` once** (B's guard — the CSS kill does not stop WAAPI/rAF): `tickTo` writes the final formatted value in one frame; `land()` swaps without fades; `roll()` falls through to its textContent path; FLIP/glide commit final positions instantly.
- Every meaning survives motion-off: flash-decay → the persistent delta glyph + color state; digit rolls → instant swap; pulse → static colored dot; ceremonies → instant state change; countdown still ticks (it is text, not animation).

## Performance budget

- Hot path: **transform / opacity / background-color / filter only.** Sanctioned one-shot exceptions: grid-rows expand (user-initiated, tiny elements) and stroke-dashoffset draw (≤6 paths, /game first paint, never looped).
- No `will-change` in the stylesheet — WAAPI promotes layers itself, and all list motion uses WAAPI so nothing persists as a compositor layer.
- Timers: the existing 15s `Desk.tick` heartbeat owns refetch checks + "ago" labels; the 1s /picks countdown is the only other timer. Zero new persistent loops.
- Witnessed-refresh choreography ≤1.2s total, overlapping (flash ∥ roll ∥ announce ∥ glide), never sequential.
- FLIP capped at 40 rows; >20 changed cells → status-strip announce only.
- Infinite animations sitewide after this work: exactly the existing gated header pulse + shimmer (Playwright screenshots stay deterministic).
- Total added JS ≈ 250 lines vanilla, zero dependencies. Verify `linear()` fallback ordering renders in the user's local macOS 12 browsers.

## Ship order

**TONIGHT (one sitting, zero re-render surgery, felt in every session):** token block (#0) + micro sweep (#1) + `Desk.land()` handoff (#2) + rail slide/crossfade (#3) + live countdown (#4). Pure perceived-quality lift — the site goes from "static HTML" to "designed instrument" before any diffing infrastructure exists. ~60 lines CSS, ~40 lines JS.

**THIS WEEK:** row expand fix (#5, also fixes the analyst-answer destruction bug) → keyed rows + FLIP (#6) → analyzer two-beat (#10). Regression-test row-expand + search + sort interleavings on research/props before shipping — these touch the most stateful render paths.

**WITH THE SEPT LAUNCH (the brand):** witnessed-change engine (#7) → pin glide + fair-post breath (#8) → timeline draw + range crossfade (#9) → kickoff ceremony (#11, must be tested before the next real seal-open window). Build the stage first; the rare show ships last, behind the most QA against the never-on-load rule.

## Risks

1. **Honesty drift** — one refactor that animates on hydration turns the brand into a lie; the `prev===null` guard is documented as a contract comment and every animation call is code-reviewed against the trigger list (user action / witnessed diff / real clock).
2. **The refetch scheduler is new surface** — compare `generated_at` only, no-op silently on unchanged payloads, never swap content under a mid-scroll reader (quiet banner instead), no competing timers.
3. **Keyed-row refactor blast radius** — ship behind small helpers with the wholesale path as fallback; test the research.html in-flight-answer preservation case specifically.
4. **Spring overshoot** — `--e-glide` capped at ~2%; any visible bounce on a probability pin reads as toy physics on a trust product; when in doubt, drop to `--e-out`.
5. **Ceremony guards** — sessionStorage keys must include event/week id.
6. **Compat** — `--e-glide` fallback declared first for pre-2023 Safari; no View Transitions anywhere (one code path, no support matrix); verify on the macOS 12 dev machine that fallbacks look intentional, not merely present.