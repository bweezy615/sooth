# W02 dry run — the first slate to carry a spread play

*Backlog item 4. Run 2026-08-27. **Nothing was sealed.***

> **RE-RUN 2026-09-03, read-only. Still nothing sealed.** The payload is
> unchanged except for one figure that moved for a known and correct reason —
> the kickoff timezone fix. See "Re-run" at the bottom.

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

---

## Re-run — 2026-09-03, overnight, read-only

`python scripts/slate_probe.py --season 2026 --week 2 --mocks`, six days before
W02 seals. Nothing was sealed, `seal.yml` was not dispatched, and `data/ledger`
was fingerprinted independently of the probe's own check — `sha256` over every
file in the tree, taken before and after by hand, both
`3c760418ef3c8312…`. Byte-identical. The probe's internal check also passed.
The four `_mock-w02*.json` fixtures it writes are gitignored and `git status`
came back clean.

### What is unchanged from 2026-08-27

Everything that decides the play:

```
slate       : 2026-W02-nfl  (16 games, 32 sealed predictions)
qualified   : 1 of 16
  PLAY CIN at HOU  line 2.5  margin 6.85  edge +4.35  HOU
       MIA at SF   line 10.5 margin 6.64  edge -3.86  MIA (dog)
       IND at KC   line 6.5  margin 3.27  edge -3.23  IND (dog)
```

The qualified play, its margin and its edge are identical to the first run, to
the last decimal. So are the two next-widest edges, so the 4-point boundary
still behaves the same way. Both sign-convention spot checks reproduce exactly:
`PHI at TEN, line −4.5, margin −6.97, edge −2.47` picks the away side and
does not mark it a dog; `SEA at ARI, line −10.0, edge +0.41` picks the home
side and marks it a dog. The probe is still deterministic — two runs on the
same evening produced the same root.

### What moved, and why it is right

| | 2026-08-27 | 2026-09-03 |
|---|---|---|
| first kick | `2026-09-17T20:15:00+00:00` | `2026-09-18T00:15:00+00:00` |
| throwaway root | `7983be56…8971` | `4ac77cf8…42dd` |

Four hours, and the fix is `0f16972a` ("kickoffs were the Eastern league clock
wearing a UTC label", 2026-09-01). nflverse publishes `gameday`/`gametime` in
US/Eastern and `_kickoff` was stamping them `tzinfo=utc` with no conversion, so
every NFL kickoff was four hours early in summer. The old value read Thu
2026-09-17 **4:15 PM** Eastern; the new one reads **8:15 PM** Eastern, which is
the Thursday-night slot. The first run's kickoff was wrong and this one is
right.

The root moved because `_kickoff` feeds `Prediction.created_at`, which is inside
the merkle leaf. That is expected, not alarming: the root here is a throwaway
built with a random `PRO_PAYLOAD_KEY` and anchored to nothing.

The same fix already worked its way through the real ledger by the versioning
path rather than by an edit. `2026-W01-nfl` now carries five commitment
versions, and v4 is where the correction lands:

```
v1  root d081c00f…  kick 2026-09-09T20:20:00+00:00
v2  root 4136512c…  kick 2026-09-09T20:20:00+00:00
v3  root 438f3607…  kick 2026-09-09T20:20:00+00:00
v4  root bc4cfd1f…  kick 2026-09-10T00:20:00+00:00   <- timezone fix
v5  root 7ba32f76…  kick 2026-09-10T00:20:00+00:00
```

W01's corrected kickoff is Wed 2026-09-09 8:20 PM Eastern. Superseding a root
with a new version is the path this system was built for; editing v3 in place
would have looked exactly like the tampering the tree exists to disprove.

### The three "found while doing it" items

1. **`EDGE_BAR = 4` hand-typed in `picks.html`** — **closed**.
   `tests/test_figures_published.py::test_the_edge_bar_is_the_same_number_in_all_three_places`
   now ties the page's `var EDGE_BAR`, `engine.models.ensemble.EDGE_THRESHOLD`
   and `_figures.json`'s `selectivity.rule_threshold_pts` together.
2. **`picks.html` hand-types 49.8%, 2,608, 52.38%, 53.2%** — **closed**.
   `picks.html` is one of the seven pages pinned by
   `test_the_hand_written_pages_quote_the_generated_figures`.
3. **The spread play is not in the Merkle commitment** — **still open, still
   Branden's**. The 32 sealed leaves are moneyline predictions; `ats` lives only
   in the display payload and the encrypted pro blob. Unchanged by this re-run
   and unchanged by the timezone fix. Nobody should act on it without Branden,
   because the fix would change what a commitment contains.

### Read this before W02 seals

The payload is correct as of tonight and W02 seals the Wednesday after the
2026-09-09 kickoff. The one thing worth knowing is that the timezone fix has
not yet been through a W02 seal, only through W01's re-commitments — so the
first W02 seal will be the first time a slate is sealed with correct kickoffs
from the start. Nothing about the probe suggests that is a problem; it is
simply the thing that is new.
