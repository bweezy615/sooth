"""Post Sooth's analysis to Discord — the community arm of the alert pipeline.

Sibling of engine.alert_email: the detection is already done, this is delivery.
What it posts, and what it deliberately refuses to post, is the whole design.

**A prop earns a post by ANALYSIS, never by price gap.**

props.json carries two very different numbers and conflating them is how a
research product turns back into a line-shopping product by accident:

  - ``gain_pts``          best book vs worst book. Arithmetic about the market.
                          Real money, but it is not a read on the game and it
                          is not ours — anyone with a price screen sees it.
  - ``model.delta_pts``   our projected probability minus the de-vigged market
                          probability. That IS the analysis: a claim about the
                          outcome that the market prices differently.

Only the second one ranks here. A prop with no ``model`` block has not been
analysed by us, so it cannot be posted as an edge — it goes out (if at all)
labelled as what it is. That rule is enforced in code, not in a style guide,
because the pressure to post a fat ``gain_pts`` number on a slow slate is
exactly when the distinction stops being observed.

The de-vigged market number is kept in every post on purpose. It is not the
product — it is the scoreboard. An edge quoted without the price it is an edge
*against* is unfalsifiable, which is precisely the thing every pick seller
sells. Publishing both is what makes the later grade mean something.

**Tiering** (free = props, pro = props + game lines):
  - free webhook  -> player props, analysis-ranked
  - pro webhook   -> the same props, plus game-line divergence alerts, which
                    stay the paid flagship exactly as engine.alert_email has
                    them today.

Dedup is a committed watermark (data/discord_sent.json), same discipline as
alerts_sent.json: the record of "posted" lives in git next to the evidence, so
overlapping cron ticks can never double-post.

    python -m engine.alert_discord --dry-run          # render, post nothing
    python -m engine.alert_discord --tier free
    python -m engine.alert_discord --tier pro --min-delta 4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

PROPS = "site/public/data/props.json"
WATERMARK = "data/discord_sent.json"
UA = "sooth-discord/1.0"

# Posting is OPT-IN PER MARKET, and each entry carries its own thresholds.
#
# delta_pts is not a comparable unit across models, even though every model
# emits the same key. What it means depends on the per-unit error of the model
# that produced it. Four points from a model whose per-player error is ~+-1
# point is a signal; the same four points from a model erring ~+-3.5 is the
# error term wearing an edge's clothes. Worse, when a market is efficient
# enough to track realised rates, ranking by delta selects the players OUR
# MODEL FITS WORST rather than the ones the market prices worst — sorting by
# delta becomes sorting by model error.
#
# That was measured, not theorised: tbconv-v1 backtested well in aggregate
# (predicted 43.3% vs actual 44.4% at the 1.5 line) while carrying ~+-3.5
# points of per-player error, with the two tails cancelling so the aggregate
# looked clean. Its three largest deltas on a live board all belonged to
# players the model over-stated against their own realised rate, while the
# market sat within a point of it.
#
# So a market cannot post until somebody has looked at that model's error and
# written a floor that clears it. An unlisted market posts NOTHING — no flag,
# no default, no exception. Adding a key here is a review-able claim that the
# error has been measured.
#
# min_obs targets roughly 100 underlying opportunities, because "a game" is not
# a constant unit of evidence: a pitcher's start is ~22 batters faced, a
# hitter's game is ~4 plate appearances.
POSTABLE: dict = {
    # EMPTY, AND ON CURRENT EVIDENCE PERMANENTLY SO.
    #
    # This is not a threshold that needs tuning or a model that needs another
    # pass. Measured on the population it would actually deploy on, the signal
    # is not there.
    #
    # THE DEPLOYMENT POPULATION IS THE WHOLE POINT. Books do not hang props
    # uniformly and engine.props requires 3+ two-sided books, so the props that
    # reach a board are the ones the market has thought hardest about — not a
    # random draw of player-games. Reconstructed from data/capture/mlb-props:
    # 3207 raw strikeout quotes -> 267 pitcher-games that actually reached a
    # board -> 194 with a known outcome.
    #
    #   kpoisson-v1 worst bucket, general population, after slope fix:  2.6 pts
    #   kpoisson-v1 worst bucket, deployment population:               18.5 pts
    #
    # The friendly-sample validation does not transfer at all.
    #
    # THE ONE-LINE STATEMENT OF ALL OF IT. Bootstrapped information content —
    # Platt slope of outcome on the model's own log-odds, where 1.0 means
    # already calibrated and 0.0 means the output carries no information:
    #
    #   general population (all starts)  n=1482   B =  0.483
    #   board population (real props)    n= 194   B = -0.070  95% CI [-0.50, 0.35]
    #
    # The model carries real information about pitchers in general and
    # effectively none about the pitchers books choose to post. The selection
    # effect is not a caveat on the result, it IS the result.
    #
    # This also closes the "publish it as a research number rather than a bet
    # signal" option. Platt recalibration on board props does fix calibration
    # (worst bucket 22.4 -> 2.7, brier 0.2800 -> 0.2480, against the market's
    # own 4.1 / 0.2439) — but it works by DISCARDING THE MODEL: the fitted map
    # compresses every input to a near-constant 42%, with all 94 held-out props
    # landing in one bucket. A calibrated kpoisson-v1 on real board props is a
    # constant wearing a model's clothes. There is nothing to present.
    #
    # Scope caveat, stated because it is not symmetric: batter_total_bases was
    # never tested on a board population — only 160 captured quotes against
    # 3207 for strikeouts. Its exclusion rests on a slope of 0.214 measured on
    # the general population, which is weaker evidence than the strikeout case.
    #
    # THE RESULT THAT ENDS THE EDGE QUESTION:
    #
    #   predicted 46.4%   actual 43.3%   market 48.6%
    #   mean |delta| vs market            11.5 pts
    #   |delta| >= 3                      156 of 194 props
    #   our side wins those disagreements  75/156 = 48.1%
    #
    # The model disagrees with the market by 11.5 points on average and wins
    # 48.1% of those disagreements. An edge of that claimed size would show a
    # win rate far north of 50%. What falsifies it is the MAGNITUDE: this is
    # not an edge too small to measure, it is a large claimed edge that does
    # not appear. Honestly on power: n=156, SE ~4 pts, so 48.1% is within noise
    # of 50% and negative skill is NOT demonstrated — what this sample excludes
    # is the large edge an 11.5-point delta implies.
    #
    # Two dead ends recorded so nobody walks them again:
    #   - Plug-in vs predictive probabilities. Withdrawn: fitted r = 180.7, so
    #     strikeouts are near-exactly Poisson. No over-dispersion to correct.
    #   - Empirical-Bayes shrinkage of K/BF toward league, weighted by batters
    #     faced. Worse: worst bucket 28.2, win rate 40.5%. Driving tau to the
    #     search ceiling (4000 BF) still only reached slope 0.689, so shrinking
    #     the RATE cannot fix the slope at any strength. The deficiency is
    #     elsewhere in the chain, most likely expected batters faced — built
    #     from a recency-weighted last five starts, the noisiest input there is.
    #
    # Not a finding: the market itself ran 48.6% predicted against 43.3% actual
    # on this sample (+5.3, n=194, ~1.5 sigma). That is noise. It is written
    # down so that nobody later finds it in the data and reads it as a
    # discovered market bias.
    #
    # A market returns here only if a model is calibrated ON THE DEPLOYMENT
    # POPULATION and then beats the price on it. Calibration alone is not
    # sufficient and never was: a model can be perfectly honest and still have
    # nothing to say. That outcome is a result to publish, not a threshold to
    # lower.
}

# Fallbacks for an explicit override only. There is intentionally no default
# entry for an unlisted market: absence means "do not post", not "post at the
# default threshold".
DEFAULT_MIN_DELTA = 3.0
DEFAULT_MIN_OBS = 25

# Never post more than this per tick. A wall of plays reads as a pick service
# and buries the one that mattered.
MAX_PER_POST = 5

# LAUNCH.md bans these outright. Enforced here so a future template edit can't
# quietly reintroduce the register sooth was built to differentiate from.
BANNED = ("lock", "guaranteed", "guarantee", "risk-free", "riskfree",
          "insider", "sure thing", "can't lose", "cant lose")

FOOTER = ("Sooth is an odds analysis tool — not a sportsbook, not betting "
          "advice. Model probabilities are estimates and are graded publicly, "
          "win or lose. 21+. Problem gambling? Call 1-800-522-4700.")


def check_language(text: str) -> None:
    """Refuse to post anything carrying the banned register. Fails loud."""
    low = text.lower()
    for word in BANNED:
        if word in low:
            raise ValueError(f"banned word {word!r} in outgoing post: {text[:120]}")


# ---- 1. rank by analysis, not by price gap ---------------------------------

def thresholds_for(market: str, min_delta: float | None = None,
                   min_obs: int | None = None) -> dict | None:
    """Thresholds for a market, or None if it may not post at all.

    An explicit override forces the market postable — that exists for testing
    a new model head against real data, never for a scheduled run.
    """
    entry = POSTABLE.get(market)
    if entry is None and min_delta is None and min_obs is None:
        return None
    entry = entry or {}
    return {"min_delta": min_delta if min_delta is not None
                         else entry.get("min_delta", DEFAULT_MIN_DELTA),
            "min_obs": min_obs if min_obs is not None
                       else entry.get("min_obs", DEFAULT_MIN_OBS)}


def analysed_props(path: str = PROPS, min_delta: float | None = None,
                   min_obs: int | None = None) -> tuple[list[dict], dict]:
    """Every prop carrying our own model read, strongest edge first.

    A prop without a ``model`` block is skipped entirely. We have not analysed
    it, so we have nothing to say about it that the board does not already show.
    """
    try:
        data = json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    out: list[dict] = []
    skipped: dict = {}
    for board in data.get("boards", []):
        for event in board.get("events", []):
            for prop in event.get("props", []):
                model = prop.get("model")
                if not model:
                    continue                      # not analysed -> not an edge
                market = prop.get("market", "")
                gate = thresholds_for(market, min_delta, min_obs)
                if gate is None:
                    # Modelled, but this market is not cleared to post. Counted
                    # so the silence is reported rather than merely happening.
                    skipped[market] = skipped.get(market, 0) + 1
                    continue
                delta = model.get("delta_pts")
                if delta is None or abs(delta) < gate["min_delta"]:
                    continue
                # A thin sample can throw a huge delta that is mostly noise.
                # Missing sample size is treated as failing, never as passing:
                # an unknown denominator is not evidence.
                n_obs = model.get("n_starts") or model.get("n_games")
                if not isinstance(n_obs, int) or n_obs < gate["min_obs"]:
                    continue
                side = "over" if delta > 0 else "under"
                out.append({
                    "sport": board.get("label", board.get("sport", "")),
                    "event": f"{event.get('away')} @ {event.get('home')}",
                    "starts": event.get("starts", ""),
                    "player": prop.get("player", ""),
                    "market_label": prop.get("market_label", prop.get("market", "")),
                    "line": prop.get("line"),
                    "side": side,
                    "p_model": model.get("p_over") if side == "over"
                               else 1.0 - model.get("p_over", 0.0),
                    "p_market": model.get("market_over") if side == "over"
                                else 1.0 - model.get("market_over", 0.0),
                    "delta_pts": abs(delta),
                    "best_price": (prop.get(side) or {}).get("best_price"),
                    "best_book": (prop.get(side) or {}).get("best_book"),
                    "fair_price": (prop.get(side) or {}).get("fair_price"),
                    "hit": prop.get("hit") or {},
                    "n_obs": model.get("n_starts") or model.get("n_games"),
                    "version": model.get("version", ""),
                })
    out.sort(key=lambda p: p["delta_pts"], reverse=True)
    return out, skipped


def prop_key(p: dict) -> str:
    return f"{p['event']}|{p['player']}|{p['market_label']}|{p['line']}|{p['side']}"


# ---- 2. render --------------------------------------------------------------

def _odds(price: Any) -> str:
    if price is None:
        return "n/a"
    return f"+{price}" if int(price) > 0 else str(int(price))


def _hit_line(hit: dict, side: str) -> str:
    """Recent form for the side we are actually recommending.

    The game log counts OVERs. Printing that raw next to an under read is
    actively misleading — an under backed by 5 straight unders would display
    as "L5 0/5" and look like a play that has missed five in a row. Count the
    recommended side, and show it even when it argues against the model.
    """
    parts = []
    for span in ("l5", "l10", "season"):
        block = hit.get(span) or {}
        n = block.get("n")
        if not n:
            continue
        overs = block.get("over", 0)
        hits = overs if side == "over" else n - overs
        parts.append(f"{span.upper()} {hits}/{n}")
    return " · ".join(parts) if parts else "no game log"


def render_prop(p: dict) -> dict:
    """One Discord embed. Model number, market number, and the price — always
    all three, so the claim can be checked and later graded."""
    title = (f"{p['player']} — {p['market_label']} "
             f"{'o' if p['side'] == 'over' else 'u'}{p['line']}")
    desc = (
        f"**Model {p['p_model'] * 100:.1f}%**  vs  market {p['p_market'] * 100:.1f}% "
        f"*(de-vigged)*\n"
        f"Edge **{p['delta_pts']:.1f} pts** of implied probability\n\n"
        f"Best price **{_odds(p['best_price'])}** at {p['best_book'] or 'n/a'} "
        f"· fair {_odds(p['fair_price'])}\n"
        f"Recent {p['side']}: {_hit_line(p['hit'], p['side'])}\n"
        f"{p['event']} · model `{p['version']}` on {p['n_obs']} games"
    )
    check_language(title + desc)
    return {"title": title, "description": desc, "color": 0x1F8B4C,
            "footer": {"text": FOOTER}}


def render_divergence(a: dict) -> dict:
    """Game-line divergence — the Pro flagship, unchanged in substance from
    what engine.alert_email sends today."""
    title = f"{a.get('away')} @ {a.get('home')} — {a.get('market')}"
    desc = (f"**{a.get('detail', '')}**\n"
            f"{a.get('move_pts', 0):.1f} pts above the cross-book consensus "
            f"on {a.get('book')}")
    check_language(title + desc)
    return {"title": title, "description": desc, "color": 0xC27C0E,
            "footer": {"text": FOOTER}}


# ---- 3. post ----------------------------------------------------------------

def post(webhook: str, content: str, embeds: list[dict]) -> bool:
    payload = json.dumps({"content": content, "embeds": embeds[:10]}).encode()
    req = urllib.request.Request(
        webhook, data=payload, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return 200 <= r.status < 300
    except Exception as e:                      # noqa: BLE001 - report, never raise
        print(f"  discord post failed: {e}", file=sys.stderr)
        return False


def load_sent() -> set:
    try:
        return set(json.loads(Path(WATERMARK).read_text()).get("keys", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_sent(sent: set) -> None:
    Path(WATERMARK).parent.mkdir(parents=True, exist_ok=True)
    Path(WATERMARK).write_text(json.dumps({"keys": sorted(sent)[-5000:]}, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=("free", "pro"), default="free")
    ap.add_argument("--min-delta", type=float, default=None,
                    help="override every market's delta floor (also forces "
                         "unlisted markets postable — testing only)")
    ap.add_argument("--min-obs", type=int, default=None,
                    help="override every market's evidence floor (also forces "
                         "unlisted markets postable — testing only)")
    ap.add_argument("--max", type=int, default=MAX_PER_POST)
    ap.add_argument("--props", default=PROPS)
    ap.add_argument("--dry-run", action="store_true",
                    help="render and print; post nothing, record nothing")
    a = ap.parse_args()

    sent = load_sent()
    found, skipped = analysed_props(a.props, a.min_delta, a.min_obs)
    props = [p for p in found if a.dry_run or prop_key(p) not in sent]
    props = props[:a.max]

    embeds = [render_prop(p) for p in props]
    header = ("**Today's model edges** — our projection vs the de-vigged market. "
              "Every one of these gets graded here, win or lose.")

    if a.tier == "pro":
        from . import alerts as alerts_mod
        scan = alerts_mod.scan("data/capture/*/*.jsonl", min_move=2.0)
        div = scan.get("divergence", [])[:a.max]
        embeds += [render_divergence(d) for d in div]
        print(f"props: {len(props)}  divergence: {len(div)}")
    else:
        print(f"props: {len(props)}")

    if not POSTABLE:
        print("  NO MARKET IS CLEARED TO POST — POSTABLE is empty by decision, "
              "not by accident. On the deployment population the strikeout "
              "model disagrees with the market by 11.5 pts on average and wins "
              "48.1% of those disagreements; the edge is not there. See "
              "POSTABLE.")

    # Never let a cap be silent: a market held back is a decision, and it
    # should read as one rather than looking like an empty slate.
    for market, n in sorted(skipped.items()):
        print(f"  held back: {n} modelled {market} prop(s) — market not cleared "
              f"to post (see POSTABLE)")

    if not embeds:
        print("nothing above threshold — posting nothing.")
        return 0

    if a.dry_run:
        print(json.dumps({"content": header, "embeds": embeds}, indent=1))
        return 0

    env = "SOOTH_DISCORD_WEBHOOK_PRO" if a.tier == "pro" else "SOOTH_DISCORD_WEBHOOK_FREE"
    webhook = os.environ.get(env, "")
    if not webhook:
        # Not an error: the server may not exist yet. Say so loudly and exit
        # clean so a scheduled run stays green until the secret is added.
        # Nothing is recorded as sent, so the first real run is not a backlog
        # of stale edges on games that have already started.
        print(f"{env} not set — Discord not configured yet, nothing posted.")
        return 0

    if post(webhook, header, embeds):
        save_sent(sent | {prop_key(p) for p in props})
        print(f"posted {len(embeds)} embeds to {a.tier}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
