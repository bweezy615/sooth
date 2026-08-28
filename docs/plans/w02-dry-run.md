# W02 dry run — the first slate to carry a spread play

*Backlog item 4. Run 2026-08-27. **Nothing was sealed.***

## Why

`2026-W02-nfl` seals the Wednesday after W01's 2026-09-09 kickoff and is the
first slate to carry the `ats` block — predicted margin, edge against the posted
number, and whether that edge clears the published bar — and the first to render
the SPREAD PLAY column on `/picks`. A slate seals once. Its Merkle root is
anchored to a public commit and re-sealing is not something we do, so the
payload has to be right the first time.

## How

`scripts/slate_probe.py` (added with this run — the plan for the engine change
referred to a probe that did not exist yet).

```
python scripts/slate_probe.py --season 2026 --week 2 --mocks
```

`build_slate` takes an `out_root` and writes everything beneath it, so the probe
points it at a temp directory. It fingerprints the real `data/ledger` before and
after and aborts if a byte moved; `PRO_PAYLOAD_KEY` is a throwaway random key so
the live one is never read. Both runs reported the real ledger unchanged at
`87767b7193aa4ac7…`.

## Payload: correct

```
slate       : 2026-W02-nfl  (16 games, 32 sealed predictions)
merkle root : 7983be56…8971   <- throwaway, not anchored
first kick  : 2026-09-17T20:15:00+00:00
qualified   : 1 of 16
```

- 32 leaves = 2 models x 16 games, as W01.
- Every game carries `ats`: `pred_margin`, `edge`, `pick`, `underdog`,
  `qualified`. W01 has none of these, which is what the engine plan intended.
- `divergence_rank` survives on every game — the sealed W01 payload,
  `picks.html` and `test_pickengine_payloads.py` all still read it.
- `ats_rank` is `1` on the one qualified play and `null` everywhere else:
  qualified plays are ranked among themselves, not within the slate.
- Exactly one game clears the 4-point bar — CIN at HOU, line 2.5, predicted
  margin 6.85, edge +4.35, play HOU. The next widest are −3.86 and −3.23, so
  the boundary behaves.
- Sign convention checks out on both bases. `spread_line` is on the home basis:
  `PHI at TEN, line −4.5, margin −6.97, edge −2.47` picks the away side (PHI)
  and correctly marks it *not* a dog; `SEA at ARI, line −10.0, edge +0.41`
  picks the home side and marks it a dog.
- The probe is deterministic: two runs produced the same root.

## Render: correct

`picks.html` driven against the probe's fixtures at three states.

- **open** — SPREAD PLAY shows `HOU +4.3` in the play style; every other row
  shows its edge dimmed. The qualified play sorts to the top, the rest keep
  `divergence_rank` order. Banner: "1 play on this slate of 16 games."
- **locked** (the fail-closed teaser, which now renders only when the pro blob
  cannot be decrypted) — board frosted, SEALED chips, no side shown, and
  "1 of 16 games cleared the engine's 4-point bar. How many is public; which
  side is not."
- **zero plays** — "No play on this slate. Nothing here sits 4 points off the
  posted number — the furthest we get is 3.9." The state the engine is
  explicitly allowed to reach renders as a finding, not as an error.

No console errors beyond a `/favicon.ico` 404 that production returns too.

## Found while doing it

1. **`EDGE_BAR = 4` is hand-typed in `picks.html`**, duplicated from
   `engine.models.ensemble.EDGE_THRESHOLD` and published as
   `selectivity.rule_threshold_pts`. If they ever diverge the page contradicts
   itself, and I saw it do exactly that: an early fixture that left a 4.35-point
   edge on a slate marked no-play rendered "nothing sits 4 points off the number
   — the furthest we get is 4.3".
2. **`picks.html` hand-types 49.8%, 2,608, 52.38% and 53.2%** in the hero and in
   the play banner. Those are `_figures.json`'s numbers, and the page fetches
   `figures.json` at runtime already. Hard rule 1.
3. **The spread play is not in the Merkle commitment.** The 32 sealed leaves are
   moneyline predictions; `ats` lives only in the display payload and the
   encrypted pro blob. The blob is committed to a public repo so its git
   timestamp does commit to it — but that is a different mechanism from the root
   `/verify` walks a reader through, and the locked view's copy ("what is sealed
   is which side we took and how strongly — already hashed into the root above")
   sits immediately above the qualified-play count. **Branden's call**, because
   the fix would change what a commitment contains.

(1) and (2) are fixed separately. (3) is reported, not acted on.

## Not done, deliberately

Nothing was sealed, no commitment was written outside the temp root, and
`data/ledger` is byte-identical to where it started.
