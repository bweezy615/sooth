# PlayerProps.ai feature clone — design

Date: 2026-08-08
Branch: `feat/playerprops-clone`
Owner decision: build the literal playerprops.ai feature set into sooth.bet.

## Goal

Port three playerprops.ai features onto sooth's existing static stack:

1. **AI Predictor page** — model projection vs. posted line, per game/player.
2. **Props comparison grid** — same player prop across every book, best number highlighted.
3. **Ask AI read-a-bet** — user submits a bet, gets an instant AI read.

## Constraints inherited from the codebase (non-negotiable)

- **Static site.** Pages are HTML in `site/public/`, styled by `assets/sooth.css`,
  with a per-page `<style>` block. `assets/shell.js` injects nav + footer and
  exposes helpers (`esc`, `sig`, `since`). Pages fetch `/data/*.json` and render
  client-side. Vercel `outputDirectory = site/public`, `framework: null`,
  `cleanUrls: true`.
- **Serverless** functions live in `/api` at repo root (Vercel picks them up
  regardless of `outputDirectory`). This is the only non-static piece.
- **Compliance floor (PRODUCT.md).** Confidence caps at 85%. Never the words
  guaranteed / lock / risk-free / insider / sure thing. Every board is timestamped.
  RG helpline already lives in the shell footer. Any fabricated marketing stat
  (e.g. "500x more likely to win") stays a `PLACEHOLDER` in HTML — owner fills it,
  code never invents a false performance number.

## Owner decisions

- **Ask AI backend:** Vercel serverless function + Claude (approved, cost accepted).
- Feature clone is literal; only deviation is the placeholder rule above.

## Architecture

```
engine/props_board.py   (NEW)  raw mlb-props jsonl  ->  site/public/data/props.json
site/public/props.html  (NEW)  reads props.json          -> comparison grid
site/public/predictor.html (NEW) reads best_lines.json (+ props.json) -> projection cards
site/public/ask.html    (NEW)  POSTs to /api/ask         -> renders AI read
api/ask.js              (NEW)  Claude call, key from env -> {answer}
assets/shell.js         (EDIT) add Predictor / Props / Ask to NAV
```

No new dependency for the front end. `api/ask.js` uses the Anthropic SDK
(or plain fetch to the Messages API — no SDK needed, one less dep).

## Data contracts

### `props.json` (produced by `engine/props_board.py`)
```json
{
  "generated_at": "ISO-8601",
  "sport": "mlb",
  "note": "Best available price per prop side across books.",
  "props": [
    {
      "player": "Aaron Judge",
      "team": "NYY",
      "market": "Batter Home Runs",
      "line": 0.5,
      "side": "Over",
      "quotes": [{"book": "draftkings", "price": 145}, ...],
      "best_price": 150, "best_book": "fanduel",
      "fair_prob": 0.41, "edge_pts": 2.1
    }
  ]
}
```
- Reads the latest snapshot per prop from `data/capture/mlb/mlb-props/*.jsonl`
  (append-only; take newest `observed_at` per (player, market, side)).
- `fair_prob` = de-vigged consensus (median implied prob, normalized so the two
  sides sum to 1) — same method already used for the moneyline board.
- `edge_pts` = best implied prob − fair prob, in points.

### Predictor page
- v1 reads existing `best_lines.json` (already has `our_prob`, `best_price`,
  `edge_pts`) for game-level (moneyline) projections, grouped by sport.
- Player-prop projections appear once `props.json` exists (reuses `fair_prob`).
- Confidence display capped at 85%.

### `/api/ask` request/response
- Request: `POST {"question": "<= 500 chars"}`.
- Server loads current `board.json` + `best_lines.json` (read from the deployed
  `site/public/data/` path or fetch its own domain), builds a prompt, calls Claude
  `claude-haiku-4-5` (cheapest; upgrade knob in one const).
- System prompt embeds the compliance floor: no guaranteed/lock language, 85% cap,
  frame as math/context not advice.
- Response: `{"answer": "..."}`. Errors return `{"error": "..."}` with a safe message.
- Security: `ANTHROPIC_API_KEY` from env only, never shipped to the browser.
  Input length capped server-side. (ponytail: no per-IP rate limiter in v1 —
  add when abuse shows up; length cap is the floor.)

## Phases

1. **Props grid** — `engine/props_board.py` + `props.json` + `props.html`.
   Delivers the most on-brand feature and unblocks predictor's player props.
2. **Predictor** — `predictor.html` on `best_lines.json`, then wire `props.json`.
3. **Ask AI** — `api/ask.js` + `ask.html`.
4. **Nav** — add three entries to `shell.js` NAV.

## Testing

- `engine/props_board.py`: one pytest with a tiny fixture `.jsonl` asserting
  newest-snapshot selection, best-price pick, and de-vig sums to 1.
- `api/ask.js`: a self-check that builds the prompt from a fixed board and asserts
  the compliance guard + board numbers are present — without calling the API.
- Front end: browser eyeball before commit (house rule: never commit UI unseen).

## Collision notes

- New engine file (`props_board.py`), not edits to `props_capture.py`, to avoid
  clashing with the `agent/engine-fix` worktree.
- All work on `feat/playerprops-clone` off `main`.

## Out of scope (v1)

- Non-MLB player props (only MLB props are captured today).
- PrizePicks optimizer, community/chat, line-movement alerts.
- Per-IP rate limiting on `/api/ask`.
