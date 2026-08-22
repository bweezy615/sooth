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
import re
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

# Never post more than this per tick. A wall of entries reads as a tout service
# and buries the one that mattered.
MAX_PER_POST = 5

# LAUNCH.md bans these outright. Enforced here so a future template edit can't
# quietly reintroduce the register sooth was built to differentiate from.
BANNED = ("lock", "locks", "guaranteed", "guarantee", "risk-free", "riskfree",
          "insider", "sure thing", "can't lose", "cant lose")

# PRODUCT.md: the paid product is "tools and data — explicitly not picks", and
# calls that load-bearing rather than cosmetic — selling tools carries no
# performance claim and therefore no FTC substantiation burden. "never a pick"
# already ships in the footer of /props, /edges and /research. What this module
# posts is selected on price against consensus, so it is not a pick in the
# forbidden sense; the words still have to match the claim.
PRODUCT_BANNED = ("pick", "picks", "play", "plays")

# Matched on WORD BOUNDARIES, not as substrings. "lock" as a substring blocks
# Tyler Lockett, and a receiver's surname taking down an entire post is a real
# outage rather than a hypothetical one. "play" as a substring would block every
# "player". The boundary is what makes the guard safe enough to leave on.
_BANNED_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in BANNED + PRODUCT_BANNED) + r")\b",
    re.IGNORECASE)

# Picks carry their own footer. The edges footer talks about model
# probabilities, and a pick is explicitly not a model output — saying so is the
# entire reason a pick may be published when the model may not.
PICKS_FOOTER = (
    "Selected on price against the de-vigged consensus of the books pricing "
    "it — not a prediction, and NOT GUARANTEED. A better number is not a "
    "promised outcome. Prices move; check the book before you bet. Sooth is an "
    "odds analysis tool, not a sportsbook, and not betting advice. 21+. "
    "Problem gambling? Call 1-800-522-4700.")

FOOTER = ("Sooth is an odds analysis tool — not a sportsbook, not betting "
          "advice. Model probabilities are estimates and are graded publicly, "
          "win or lose. 21+. Problem gambling? Call 1-800-522-4700.")


# A disclaimer has to be able to say the word it disclaims. "Nothing here is
# guaranteed" is the honest use; "guaranteed winner" is the banned one, and a
# plain word match cannot tell them apart. These exact negated phrases are
# removed before scanning, so the guard can be pointed at footers — which are
# the one place the vocabulary legitimately appears — instead of being kept
# away from them and leaving that text unchecked.
#
# Deliberately literal phrases rather than a general negation rule: a clever
# rule would eventually excuse a sentence nobody intended to allow.
ALLOWED_PHRASES = (
    "not guaranteed",
    "never guaranteed",
    "nothing here is guaranteed",
    "no guarantee",
    "not a guarantee",
)


def check_language(text: str) -> None:
    """Refuse to post anything carrying the banned register. Fails loud."""
    scan = text
    for phrase in ALLOWED_PHRASES:
        scan = re.sub(re.escape(phrase), " ", scan, flags=re.IGNORECASE)
    hit = _BANNED_RE.search(scan)
    if hit:
        raise ValueError(
            f"banned word {hit.group(0)!r} in outgoing post: {text[:120]}")


# ---- 1. rank by analysis, not by price gap ---------------------------------

def thresholds_for(market: str, min_delta: float | None = None,
                   min_obs: int | None = None) -> dict | None:
    """Thresholds for a market, or None if it may not post at all.

    An override can only TIGHTEN a market that is already listed. It cannot
    make an unlisted market postable.

    That used to be the other way round — an override forced postability, with
    a comment saying it was for testing and never for a scheduled run. PRODUCT.md
    now carries "never rank or select anything by model edge" as a hard
    constraint, and a hard constraint enforced by a comment is a convention. One
    `--min-delta 3` in a workflow file would have reopened the whole path.
    """
    entry = POSTABLE.get(market)
    if entry is None:
        return None
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


# ---- 1b. daily picks: selected on PRICE, not on the model -------------------

def daily_picks(path: str = PROPS, min_obs: int = 10) -> list[dict]:
    """Every priced side, best price against the de-vigged consensus first.

    This is a different claim from the edges path and must not be confused with
    it. It ranks on ``edge_vs_fair_pts`` — how good the best available number is
    against the consensus of the books pricing that prop. That figure does not
    depend on any model being right about anything; getting a better number on
    the same wager is arithmetic.

    It is NOT ``gain_pts``, which is best-book-vs-worst-book and only measures
    how much the books disagree with each other. A wide disagreement with a bad
    best price is not an opportunity.

    The sign is kept and never suppressed. A negative price edge means the best
    number on the board is still worse than consensus fair, which is the vig —
    normal, and the honest thing to show. Ranking still holds: least-negative is
    genuinely the best available number.
    """
    try:
        data = json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    out: list[dict] = []
    for board in data.get("boards", []):
        for event in board.get("events", []):
            for prop in event.get("props", []):
                for side in ("over", "under"):
                    s = prop.get(side) or {}
                    if s.get("best_price") is None or s.get("edge_vs_fair_pts") is None:
                        continue
                    hit = prop.get("hit") or {}
                    # A price edge on a player with four games of history is
                    # still a real price edge — but the history line printed
                    # next to it would be noise, and the history is what makes
                    # the post readable. Withhold the line, keep the pick.
                    season_n = (hit.get("season") or {}).get("n") or 0
                    out.append({
                        "sport": board.get("label", board.get("sport", "")),
                        "event": f"{event.get('away')} @ {event.get('home')}",
                        "player": prop.get("player", ""),
                        "market": prop.get("market", ""),
                        "market_label": prop.get("market_label", prop.get("market", "")),
                        "line": prop.get("line"),
                        "side": side,
                        "best_price": s["best_price"],
                        "best_book": s.get("best_book"),
                        "fair_price": s.get("fair_price"),
                        "n_books": s.get("n_books"),
                        "price_edge_pts": s["edge_vs_fair_pts"],
                        "book_spread_pts": s.get("gain_pts"),
                        "hit": hit if season_n >= min_obs else {},
                    })
    out.sort(key=lambda r: -r["price_edge_pts"])
    return out


# PRODUCT.md sets the audience as sharp and serious bettors — "density over
# persuasion, no hand-holding, no explainer tone" — and the same paragraph adds
# that "a newcomer should not be actively excluded, but nothing slows down the
# person who already knows". That is the seam this embed sits in.
#
# It goes LAST, after the prices, and only when there are prices to explain. A
# reader who knows what de-vigging is has already got what they came for and
# scrolls past; a reader who does not is not sent elsewhere to find out. No
# gloss is repeated on individual entries, because a term explained five times
# in one post is explainer tone arriving by another route.
GLOSS = {
    "title": "What these numbers mean",
    "color": 0x4F545C,
    "description": (
        "**Consensus fair** — every book builds a margin into its prices (the "
        "vig), so the prices you see add up to more than 100%. Strip that "
        "margin out across the books pricing a wager and what is left is the "
        "market's honest estimate. That is the fair number.\n"
        "**Points below/above fair** — the gap between the best price you can "
        "actually get and that fair number, in percentage points. Below fair "
        "is normal: the gap is the house's cut.\n"
        "**Books disagree by** — how far apart the best and worst prices are "
        "for the same wager. It is why the book you use matters."),
}


def pick_key(p: dict) -> str:
    return f"{p['event']}|{p['player']}|{p['market_label']}|{p['line']}|{p['side']}"


def render_pick(p: dict) -> dict:
    """One pick. The price is the claim; the model is not mentioned."""
    title = (f"{p['player']} — {p['market_label']} "
             f"{'o' if p['side'] == 'over' else 'u'}{p['line']}")
    edge = p["price_edge_pts"]
    # Never let a negative edge read as a positive one. The sentence changes,
    # not just the sign, because "edge" is the wrong word for being below fair.
    if edge >= 0:
        price_line = (f"**{edge:.2f} pts better than consensus fair** "
                      f"({_odds(p['fair_price'])}, {p['n_books']} books)")
    else:
        price_line = (f"{abs(edge):.2f} pts **below** consensus fair "
                      f"({_odds(p['fair_price'])}, {p['n_books']} books) — that "
                      f"gap is the vig, not an edge")
    parts = [
        f"**{_odds(p['best_price'])} at {p['best_book'] or 'n/a'}** — "
        f"best number on the board",
        price_line,
    ]
    if p.get("book_spread_pts") is not None:
        parts.append(f"Books disagree by {p['book_spread_pts']:.2f} pts "
                     f"(best vs worst)")
    if p["hit"]:
        parts.append(f"Recent {p['side']}: {_hit_line(p['hit'], p['side'])}")
    parts.append(f"{p['event']} · selected on price, not on a model")
    desc = "\n".join(parts)
    check_language(title + desc + PICKS_FOOTER)
    return {"title": title, "description": desc, "color": 0x3B88C3,
            "footer": {"text": PICKS_FOOTER}}


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
    check_language(title + desc + FOOTER)
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
    # "prices" is the name; "picks" is kept as a hidden synonym so any existing
    # invocation keeps working. PRODUCT.md's vocabulary rule is about surfaces a
    # reader sees, and a flag is not one — but a workflow file ends up
    # containing the literal string, and that string appears in job logs and in
    # any runbook quoting the command. Cheap to close the last place the word
    # survives on a path somebody reads.
    ap.add_argument("--mode", choices=("prices", "picks", "edges"),
                    default="prices",
                    help="prices: rank by best available price against "
                         "consensus fair (the live product). edges: DIAGNOSTIC "
                         "ONLY — ranks by model delta and can never post.")
    ap.add_argument("--top", type=int, default=None,
                    help="how many best prices to post")
    ap.add_argument("--no-gloss", action="store_true",
                    help="omit the trailing plain-English explainer embed")
    ap.add_argument("--picks", type=int, default=3,
                    help=argparse.SUPPRESS)   # hidden synonym for --top
    ap.add_argument("--min-delta", type=float, default=None,
                    help="tighten the delta floor of markets already in "
                         "POSTABLE; cannot make an unlisted market postable")
    ap.add_argument("--min-obs", type=int, default=None,
                    help="tighten the evidence floor of markets already in "
                         "POSTABLE; cannot make an unlisted market postable")
    ap.add_argument("--max", type=int, default=MAX_PER_POST)
    ap.add_argument("--props", default=PROPS)
    ap.add_argument("--dry-run", action="store_true",
                    help="render and print; post nothing, record nothing")
    a = ap.parse_args()

    sent = load_sent()

    if a.mode in ("prices", "picks"):
        found = daily_picks(a.props, a.min_obs if a.min_obs is not None else 10)
        picks = [p for p in found if a.dry_run or pick_key(p) not in sent]
        picks = picks[:(a.top if a.top is not None else a.picks)]
        if not picks:
            print("no priced sides on the board — posting nothing.")
            return 0
        embeds = [render_pick(p) for p in picks]
        if not a.no_gloss:
            embeds.append(GLOSS)
        # If nothing on the board beats consensus fair, say so at the top. The
        # post is still the best available numbers, but "best available" and
        # "better than fair" are different claims and the reader is owed which
        # one this is before reading a single pick.
        best = picks[0]["price_edge_pts"]
        if best < 0:
            header = ("**Best prices on the board.** Selected on price against "
                      "the de-vigged consensus, not on a model. Nothing on the "
                      "board beats consensus fair today, so these are where you "
                      "give up least to the vig — research, not a "
                      "recommendation. Graded here either way.")
        else:
            header = ("**Best prices on the board.** Selected on price against "
                      "the de-vigged consensus, not on a model. Research, not a "
                      "recommendation. Graded here either way, win or lose.")
        print(f"best prices: {len(picks)}  best edge vs fair: {best:+.2f} pts")
        if a.dry_run:
            print(json.dumps({"content": header, "embeds": embeds}, indent=1))
            return 0
        env = ("SOOTH_DISCORD_WEBHOOK_PRO" if a.tier == "pro"
               else "SOOTH_DISCORD_WEBHOOK_FREE")
        webhook = os.environ.get(env, "")
        if not webhook:
            print(f"{env} not set — Discord not configured yet, nothing posted.")
            return 0
        if post(webhook, header, embeds):
            save_sent(sent | {pick_key(p) for p in picks})
            print(f"posted {len(embeds)} best prices to {a.tier}")
            return 0
        return 1

    # PRODUCT.md hard constraint: never rank or select anything by model edge.
    # This path still ranks, because being able to re-measure is worth keeping
    # and the POSTABLE note is the record of why the answer was no. It simply
    # cannot publish the result, whatever the flags say. Enforced here rather
    # than left to POSTABLE being empty, so that adding a key back by mistake
    # does not silently reopen a route to a channel.
    a.dry_run = True

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
