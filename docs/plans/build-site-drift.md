# build_site.py — stop the generator reverting the site

## The failure

`scripts/build_site.py` regenerates `site/public/{methodology,verify,disclaimers,
ledger}.html`. All four have been hand-edited since the generator last matched
them, so running the script **silently reverts live work**. Measured today:
243 insertions against 440 deletions across the four files.

Concretely, running it right now would republish the pre-`3b109fa96` figures
(49.50% ATS, Brier 0.22148) on `/methodology` and delete the "This is not an
edge, and we will not describe it as one" section — on a site whose entire
positioning is that its numbers are reproducible.

The script already carries a "⚠ DRIFT WARNING" comment telling the reader to
diff first. It has been there since 2026-08-22 and did not prevent any of this,
because **a comment is not a check**. That is the actual defect. Porting the
current hand-edits up into the generator fixes today's drift; only a test that
fails on disagreement stops it recurring.

## Four classes of drift, all real

1. **Stylesheet.** The generator holds the pre-FROZEN-MARKET palette
   (hardcoded `#06080A`, `Archivo`, its own `header`/`nav`/`.brand` rules).
   The published pages map legacy token names onto desk.css tokens, drop the
   shell-clobbering rules, and add mobile table stacking plus the long-form
   measure/list-marker/doubled-rule repairs. `methodology.html` and
   `disclaimers.html` share one stylesheet; `verify.html` is that plus a
   22-line frost appendix; `ledger.html` has its own.

2. **Stale markdown sources.** `site/content/methodology.md` prose (lines
   45-47, 61) still carries the old figures while its own tables carry the new
   ones — the file contradicts itself. `methodology.md:421` and `verify.md:57,
   210` still describe the paid tier, removed 2026-08-22. **The published HTML
   is right and the source is wrong**, which is backwards and is why a rebuild
   is destructive.

3. **`build_ledger()` markup.** Emits `<div class="card">` and
   `<span class="badge sealed">`; published is `card rimlit` and
   `<span class="frost">`.

4. **`verify.html` frost treatment.** 5 `pre.frosted`, 4 `span.ice`, 1
   `span.ok` inside rendered code blocks — markdown cannot produce these, so
   they were applied to the HTML by hand and no rebuild can reproduce them.

## Changes

### Phase 1 — stylesheets into the generator
Split `CSS` into `CSS_PROSE` (the shared baseline, lifted verbatim from the
published `disclaimers.html`), `CSS_VERIFY` (the frost appendix), and
`CSS_LEDGER` (ledger's own). `PAGES` entries gain an optional extra-CSS slot.

### Phase 2 — repair the sources, not the output
Update `methodology.md` prose to the figures its own tables already carry, and
retire the paid-tier sentences in `methodology.md` and `verify.md` to match the
published copy.

### Phase 3 — `build_ledger()` emits the frost markup
`card rimlit`, `span.frost` for the seal chip and the published root.

### Phase 4 — frost post-pass for `/verify`
A render-time pass that marks the five sealed artefacts `.frosted`, wraps the
roots and the leaf fingerprint in `.ice`, and the verdict line in `.ok`. Keyed
on the artefacts themselves, not on line numbers.

### Phase 5 — the guard (the point of the exercise)
`tests/test_build_site.py`: build into a temp root, assert byte-equality with
every file under `site/public/` the generator owns. Fails the moment output and
generator disagree, in either direction. Without this the other four phases
just reset the clock.

## Acceptance
`python scripts/build_site.py && git diff --exit-code site/public/` is clean,
and the live pages are unchanged apart from the two source-copy repairs.

## Not in scope
- Making `methodology.md`'s numbers generated from `_figures.json`. The repo's
  hard rule says no published number is hand-typed; these are, and that is a
  real violation — but it is a separate change with its own blast radius.
  Logged as debt, not fixed here.
- Restyling anything. This change makes the generator agree with what is live;
  it does not change a pixel.
