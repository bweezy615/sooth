# Two pages called "Ledger"

*Backlog item 1. Written 2026-08-27 before any code.*

> **STATUS: CLOSED — all four phases shipped, re-verified live 2026-09-03.**
> Including the "not in scope" item at the bottom, which was picked up by the
> methodology pass. Evidence under "Closure". Do not re-do it.

## The defect

Two different pages answer to the same name, and the one a skeptic most needs
is the one the nav does not point at.

| | `/trust` | `/ledger` |
|---|---|---|
| `<title>` | `Sooth — Ledger` | `Ledger — Sooth` |
| `<h1>` | "The ledger, and why you can audit it." | "Ledger" |
| screen strip | `PROOF LEDGER` | — |
| what it is | an **index**: live CLV, sample populations, graded published picks, and a link card to every receipt | the **artifact**: every sealed slate, its Merkle root, its reveal, its grade, rendered straight from `data/ledger/` |
| header nav | `LEDGER` points here | not in the nav |
| footer | not linked | `Ledger` |
| homepage sidebar | not linked | linked, labelled **"Proof Ledger"** |
| homepage mobile tab | `LEDGER` points here | not linked |
| `Desk.mount()` key | `"ledger"` | `""` — the real ledger lights **no** nav item |

So the word "Ledger" currently labels three different destinations depending on
where you click it (header → `/trust`, footer → `/ledger`, sidebar "Proof
Ledger" → `/ledger`), and the page that literally is the ledger of sealed
commitments highlights nothing in the nav when you are standing on it.

For a site whose pitch is "check our arithmetic", a reader who clicks LEDGER
looking for the sealed slates and lands on an index instead has been given a
small reason to doubt everything else. That is the cost here — not a dead link.

## What each page is actually for

Read both in full. They are not duplicates and neither should be deleted:

- **`/ledger` is the primary evidence.** It is generated from `data/ledger/` by
  `build_site.py::build_ledger()` precisely so the page is a rendering of the
  same files a reader can download. "Ledger" is the correct word for it: a
  chronological record of committed entries. It keeps its name.
- **`/trust` is the index of the receipts.** Its own subhead already says so:
  "This page is the index of the receipts." It carries the two live
  measurements (CLV on sealed picks, every sample with its own denominator) and
  routes to `/ledger`, `/verify`, `/record`, `/methodology`, `/props-model`,
  `/engine`, `/gamelog`, `/disclaimers`, `/alerts`. It is the hub, and it is the
  right nav destination — a skeptic arriving cold gets the map, one click from
  every artifact. It is the page that must be renamed.

`/trust` becomes **Proof**. One word, says what the page is for, does not
collide with `/ledger`, and matches the strip that is already on the page.

## Decisions and their reasons

1. **No URL changes.** `/trust` and `/ledger` both stay. Renaming a URL would
   mean touching `sitemap.xml`, `sw.js`'s precache SHELL list, and adding a
   redirect, for zero reader benefit — the confusion is in the *labels*, not the
   paths. Surgical: change what the reader sees, leave the plumbing alone.
2. **Nav keeps one slot, relabelled `PROOF` → `/trust`.** Not two slots: the
   header nav is already ten items, and `/ledger` is one click away from both
   the hub and the footer that ships on every page.
3. **`/ledger` starts lighting the nav.** `ledger.html` mounts `""` today, so
   the real ledger is the one measurement page that leaves the nav dark. It
   joins the family.
4. **The internal key `"ledger"` is renamed to `"proof"`** across `desk.js`,
   `desk.css`, `index.html` and the five pages that mount it. Leaving a key
   named `ledger` behind a label that says PROOF re-creates the same ambiguity
   one layer down, for the next reader of the code. It is a mechanical rename
   with no behaviour change, covered by `desk.selfcheck.js`.
5. **The homepage sidebar's "Proof Ledger" becomes "Ledger."** It points at
   `/ledger`, so it should use that page's actual name; "Proof Ledger" was the
   third variant of the word and now would collide with the new nav label.

## Phases

**Phase 1 — the hub renames itself.** `site/public/trust.html`:
`<title>` → `Proof — Sooth`; strip name `PROOF LEDGER` → `PROOF`; `<h1>` → "Every
number we publish, and where to check it."; receipts card `PUBLIC LEDGER` →
`THE SEALED LEDGER`; `D.mount("ledger")` → `D.mount("proof")`.
Verify: browser, and the h1/title read as one page.

**Phase 2 — the shell agrees.** `desk.js` NAV + TABS label `LEDGER` → `PROOF`
and key → `proof`; `desk.css` + `index.html` `.m-ti[data-i="ledger"]` →
`[data-i="proof"]`; `index.html` mobile tab label + `data-i`; `index.html`
sidebar `Proof Ledger` → `Ledger`. Update `tests/frontend/desk.selfcheck.js`
expectation `["/trust", "LEDGER"]` → `["/trust", "PROOF"]`.

**Phase 3 — the ledger joins the family.** `build_site.py` gains `"ledger":
"proof"` in a mount-key map so `ledger.html` renders
`window.Desk.mount("proof")`, then rebuild. This is a generated page — edit the
generator, never the HTML (see the repo's own lesson).

**Phase 4 — the check that keeps it fixed.** Extend
`tests/frontend/desk.selfcheck.js`: assert no two nav labels are equal, and that
exactly one nav entry carries the word LEDGER/PROOF. Add a pytest in
`tests/test_build_site.py`'s neighbourhood asserting `/trust` and `/ledger` do
not share a `<title>` name — the specific thing that was wrong. A comment saying
"don't call two pages the same thing" is not a check.

## Risk

Low. No URL, no data, no sealed artifact, no published figure is touched.
The one thing that could regress is nav highlighting, which
`desk.selfcheck.js` already covers and Phase 4 strengthens.

## Not in scope, found while reading (logged, not fixed here)

`site/public/trust.html`'s `.stance` block hand-types the backtest record —
`2,671` graded, `2,608` decided, `63` pushes, `49.8%` us, `49.7%` market,
`52.4%` breakeven. Checked against `site/content/_figures.json` today: all six
are **correct**. But they are hand-typed and no test pins them, which is hard
rule 1 ("no published number is ever hand-typed") and exactly the shape of the
19-day-stale `figures.json` failure. Belongs with backlog item 3, which wires
`methodology.md`'s hand-typed figures to `_figures.json`; `trust.html` should be
pinned in the same pass.

---

## Closure — verified 2026-09-03, overnight run

All four phases are in, and the word "Ledger" now labels exactly one
destination. Verified in production, not from the git log — fetched from
sooth.bet:

| what | live value |
|---|---|
| `/trust` `<title>` | `Proof — Sooth` |
| `/ledger` `<title>` | `Ledger — Sooth` |
| `/ledger` mount call | `Desk.mount("proof")` — the sealed ledger lights the nav |
| live `desk.js` nav slot | `href:"/trust", key:"proof", label:"PROOF"` |

Phase 4's checks both exist: `tests/test_page_names.py` (four tests) and the
one-label-one-destination block in `tests/frontend/desk.selfcheck.js`.

### The guards, watched failing

Each was made to fail and then reverted:

| Guard | Fault injected | Result |
|---|---|---|
| `test_no_two_pages_share_a_name` + `test_the_ledger_is_the_page_that_is_called_the_ledger` | retitled `/trust` back to `Sooth — Ledger` | **2 FAILED** — and note the brand-affix regex did its job: it saw "Sooth — Ledger" and "Ledger — Sooth" as the same name, which is exactly how the original collision survived review |
| `test_the_ledger_lights_the_nav_entry_that_leads_to_it` | emptied `MOUNT` in `build_site.py` and rebuilt | **FAILED**, with a message pointing at the generator rather than the HTML |
| `desk.selfcheck.js` one-label-one-destination | relabelled the `/trust` nav slot `ALERTS`, colliding with `/alerts` | **FAILED** (assert.fail, non-zero exit) |

The generator was restored and the site rebuilt after fault B; `git status` is
clean.

### The "not in scope" item is also closed

`trust.html`'s `.stance` block still hand-types the backtest record, as this
file predicted it would. It is no longer unpinned:
`tests/test_figures_published.py::test_the_hand_written_pages_quote_the_generated_figures`
now checks all six of those values against `_figures.json`, along with six
other hand-written pages. Confirmed failing in the same session by injecting a
stale record into methodology.md's sibling guard.
