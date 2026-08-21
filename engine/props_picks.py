"""Daily prop picks, selected on price rather than on model edge.

Which props to publish is a selection question, and the selection mechanism is
the whole product. Two candidates were available and they are not equally good:

  model.delta_pts   our probability minus the market's. Measured on 194 real
                    board props: an average disagreement of 11.5 points with a
                    48.1% win rate on the 156 we disagreed on by 3+. Ranking by
                    it sorts by our own error. See
                    docs/reports/props-model-negative-result.md.

  edge_vs_fair_pts  how much better the best available price is than the
                    de-vigged consensus of the books pricing it. This does not
                    depend on our model being right about anything. Getting a
                    better number on the same wager is better arithmetic, not a
                    forecast.

This module ranks on the second. Vig means the figure is usually negative — the
consensus fair price is better than any real price, because that is how books
make money — so the pick is the prop where you give up the least to the vig,
and a positive figure means the best book is hanging a number better than its
peers' own consensus.

What is published alongside each pick is history and price, not prediction:
the player's actual over-rate in his last 5, last 10 and season starts. Those
are counts of things that happened. The model's probability is carried when
present and clearly marked as non-predictive, because on this population it
measurably is.

    python -m engine.props_picks              # write json + print the post
    python -m engine.props_picks --top 3
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

DISCLAIMER = ("Best available price at time of posting, not a prediction. "
              "Prices move and nothing here is guaranteed. "
              "Our own prop model showed no edge on props books post — "
              "sooth.bet/props-model.")

MIN_BOOKS = 3

# Games of history required before the form line is published beside a pick.
# A price edge on four games is a real price edge; the form line next to it
# would be noise, so the pick still posts and the history is withheld. Per
# market, because a game is not a constant unit of evidence — a hitter reaches
# 25 games in under a month, a starter needs most of a season. An unmapped
# market takes the STRICTEST floor rather than the loosest, so a new market
# cannot arrive publishing thin history because nobody remembered to tune it.
MIN_FORM_GAMES = {
    "pitcher_strikeouts": 5,
    "batter_total_bases": 25,
}
DEFAULT_MIN_FORM = max(MIN_FORM_GAMES.values())


def price_sentence(edge_pts: float) -> str:
    """The sign changes the claim, so it changes the sentence.

    A price below consensus fair is not a small edge, it is the vig. Letting a
    minus sign be the only thing separating "you are getting a good number" from
    "you are paying the house" invites exactly the misreading this whole product
    is supposed to avoid.
    """
    if edge_pts > 0:
        return f"{edge_pts:.2f} pts better than consensus fair"
    return (f"{abs(edge_pts):.2f} pts below consensus fair "
            f"— that gap is the vig, not an edge")


def american(p: float) -> str:
    return f"+{int(p)}" if p > 0 else f"{int(p)}"


def side_rows(doc: dict) -> list[dict]:
    """One row per (prop, side) with everything a pick needs."""
    rows = []
    for board in doc.get("boards", []):
        for ev in board.get("events", []):
            for p in ev.get("props", []):
                hit = p.get("hit") or {}
                model = p.get("model") or {}
                for side in ("over", "under"):
                    s = p.get(side) or {}
                    if s.get("n_books", 0) < MIN_BOOKS:
                        continue
                    if s.get("best_price") is None or s.get("edge_vs_fair_pts") is None:
                        continue
                    rows.append({
                        "sport": board.get("sport"),
                        "matchup": f"{ev.get('away')} @ {ev.get('home')}",
                        "starts": ev.get("starts"),
                        "player": p.get("player"),
                        "market": p.get("market"),
                        "market_label": p.get("market_label"),
                        "line": p.get("line"),
                        "side": side,
                        "best_price": s["best_price"],
                        "best_book": s.get("best_book"),
                        "n_books": s.get("n_books"),
                        "fair_price": s.get("fair_price"),
                        "price_edge_pts": s["edge_vs_fair_pts"],
                        "book_spread_pts": s.get("gain_pts"),
                        "hit_l5": hit.get("l5"),
                        "hit_l10": hit.get("l10"),
                        "hit_season": hit.get("season"),
                        "model_p_over": model.get("p_over"),
                        "model_version": model.get("version"),
                    })
    return rows


def hit_str(row: dict) -> str | None:
    """Realised rate for the side being picked. None when the sample is too thin.

    Returns None rather than a short line: the pick is still worth posting on
    price alone, but a form line built on a handful of games reads as evidence
    and is not.
    """
    season = row.get("hit_season") or {}
    floor = MIN_FORM_GAMES.get(row["market"], DEFAULT_MIN_FORM)
    if season.get("n", 0) < floor:
        return None
    parts = []
    for label, key in (("L5", "hit_l5"), ("L10", "hit_l10"), ("SZN", "hit_season")):
        h = row.get(key)
        if not h or not h.get("n"):
            continue
        over = h.get("over", 0)
        made = over if row["side"] == "over" else h["n"] - over
        parts.append(f"{label} {made}/{h['n']}")
    return "  ".join(parts) if parts else None


def pick(doc: dict, top: int = 5) -> list[dict]:
    rows = side_rows(doc)
    # Best price first. One side per player-line: publishing both sides of the
    # same prop is not two picks, it is a hedge with extra steps.
    rows.sort(key=lambda r: -r["price_edge_pts"])
    seen = set()
    out = []
    for r in rows:
        k = (r["player"], r["market"], r["line"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
        if len(out) >= top:
            break
    return out


def render(picks: list[dict], generated_at: str | None) -> str:
    if not picks:
        return ("No props cleared the board today — fewer than "
                f"{MIN_BOOKS} books on both sides. Nothing to post.\n\n"
                + DISCLAIMER)
    lines = ["BEST PRICES ON THE BOARD"]
    if generated_at:
        lines.append(f"board as of {generated_at[:16].replace('T', ' ')} UTC")

    # State the day's situation before the first pick is read. Whether these are
    # value plays or damage control is the most important thing on the page, and
    # a reader should not have to infer it from a minus sign three lines down.
    beat = sum(1 for r in picks if r["price_edge_pts"] > 0)
    if beat == 0:
        lines.append("Nothing on the board beats consensus fair today. "
                     "These are where you give up least to the vig, "
                     "not positive-value plays.")
    elif beat < len(picks):
        lines.append(f"{beat} of {len(picks)} beat consensus fair today. "
                     "The rest are where you give up least.")
    else:
        lines.append("All of today's picks are priced better than consensus fair.")
    lines.append("")

    for i, r in enumerate(picks, 1):
        lines.append(f"{i}. {r['player']} {r['side'].upper()} {r['line']} "
                     f"{(r['market_label'] or r['market']).lower()}")
        lines.append(f"   {american(r['best_price'])} at {r['best_book']}"
                     f"   (consensus fair {american(r['fair_price'])}, "
                     f"{r['n_books']} books)")
        lines.append(f"   {price_sentence(r['price_edge_pts'])}")
        form = hit_str(r)
        if form:
            lines.append(f"   history: {form}")
        if r.get("model_p_over") is not None:
            side_p = (r["model_p_over"] if r["side"] == "over"
                      else 1 - r["model_p_over"])
            lines.append(f"   our model says {side_p*100:.0f}% "
                         f"(context only — measured no edge on props)")
        lines.append(f"   {r['matchup']}")
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--props", default="site/public/data/props.json")
    ap.add_argument("--out", default="site/public/data/props_picks.json")
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()

    doc = json.loads(Path(a.props).read_text())
    picks = pick(doc, a.top)
    payload = {
        "generated_at": doc.get("generated_at"),
        "selection": "edge_vs_fair_pts",
        "selection_note": ("ranked by best available price against de-vigged "
                           "consensus, NOT by model edge — the model measured "
                           "no edge on props books post"),
        "disclaimer": DISCLAIMER,
        "n_considered": len(side_rows(doc)),
        "picks": picks,
    }
    out = Path(a.out)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1))
    os.replace(tmp, out)
    print(render(picks, doc.get("generated_at")))


if __name__ == "__main__":
    main()
