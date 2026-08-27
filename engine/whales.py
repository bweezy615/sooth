"""Capture checkable Polymarket sports-futures positions and trades.

    python -m engine.whales
    python -m engine.whales --selfcheck

The output reports public ledger activity. It does not interpret that activity
or identify the people behind public wallet addresses.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"
SPORTS = ("nfl", "nba", "mlb", "nhl", "sports")
LIMIT = 100
WHALE_MIN_USD = 10_000.0

# One capture is three calls per market across a few hundred markets, and the
# first unpaced run came back 429 Too Many Requests partway through. Polymarket
# publishes no rate limit, so this follows engine/capture.py: pace every call,
# and back off rather than abandoning a run that is most of the way done.
PAUSE = 0.2
RETRIES = 4
BACKOFF = 3.0
# Transient by definition: 408 the server gave up waiting, 425 it wants us to
# slow down, 429 we asked too fast, 5xx it broke. Everything else -- a 404, a
# 400 -- is a fact about the request and retrying it just wastes the run.
RETRY_STATUS = {408, 425, 429}

# Deepest the capture will look. Discovery finds ~640 qualifying markets and
# each costs three calls, so the uncapped run was ~1,900 requests against an
# undocumented free API -- two of three runs died mid-flight before the retry
# logic existed.
#
# The cut is a real trade, not free. Whale money is NOT concentrated in the
# busiest markets: measured against a full snapshot, the top 200 by 24h volume
# hold 70% of the qualifying value and 51% of the rows, the top 60 only 30%.
# Ranking by open interest is worse (top 60 = 22%), so volume it is. Raise this
# to look deeper and pay for it in requests; the page reports the depth.
MARKET_CAP = 200
OUT = Path("site/public/data/whales.json")

READER_COPY = (
    "Public Polymarket sports-futures positions and trades.",
    "Current value is shares multiplied by the latest outcome price.",
)
BANNED = re.compile(
    r"\b(?:back(?:ing)?|fad(?:e|ing)|smart money|bet on|tail me|lock|"
    r"guaranteed|risk-free|insider|sure thing|value play)\b", re.I
)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []
    return []


def _display(row: dict) -> str:
    return str(row.get("name") or row.get("pseudonym") or "").strip()


def _wallet(row: dict) -> str:
    return str(row.get("proxyWallet") or "").strip()


def _get(session: requests.Session, url: str, **params: Any) -> Any:
    """One paced request, retried on rate limits and transient server errors.

    A 429 halfway through means the whole capture is thrown away and the page
    keeps a stale snapshot, so being a slow guest beats being a rejected one.
    Retry-After is honoured when the server sends it; otherwise the wait grows
    geometrically. Anything that is not 429/5xx still raises immediately —
    a 404 is not going to fix itself.
    """
    delay = BACKOFF
    for attempt in range(RETRIES + 1):
        time.sleep(PAUSE)
        try:
            response = session.get(url, params=params, timeout=45,
                                   headers={"accept": "application/json"})
        except (requests.Timeout, requests.ConnectionError):
            # over a thousand calls a run, a dropped connection is a certainty
            # eventually; it should cost one retry, not the whole capture
            if attempt == RETRIES:
                raise
            time.sleep(delay)
            delay *= 2
            continue
        if response.status_code in RETRY_STATUS or response.status_code >= 500:
            if attempt == RETRIES:
                response.raise_for_status()
            wait = _number(response.headers.get("Retry-After"), 0.0) or delay
            time.sleep(min(wait, 60.0))
            delay *= 2
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("unreachable")


def discover(session: requests.Session, gamma_base: str = GAMMA,
             threshold: float = WHALE_MIN_USD, cap: int = MARKET_CAP) -> list[dict]:
    """Discover and deduplicate recent open markets; explicit tags win.

    Returns at most `cap` markets, the busiest first by 24h volume, then sorted
    by condition id so the published file stays diff-stable run to run.
    """
    found: dict[str, dict] = {}
    for sport in SPORTS:
        # ponytail: bounded discovery; paginate if the product needs archives.
        events = _get(session, f"{gamma_base}/events", closed="false",
                      tag_slug=sport, limit=LIMIT, order="volume24hr",
                      ascending="false")
        if not isinstance(events, list):
            raise ValueError(f"Gamma returned malformed {sport} events")
        for event in events:
            for market in event.get("markets") or []:
                condition_id = str(market.get("conditionId") or "").strip()
                volume = _number(market.get("volumeNum") or market.get("volume"))
                if (not condition_id or market.get("closed") is True
                        or market.get("sportsMarketType") or volume < threshold):
                    continue
                candidate = {
                    **market,
                    "conditionId": condition_id,
                    "eventSlug": market.get("eventSlug") or event.get("slug"),
                    "_sport": sport,
                    "_volume": volume,
                }
                previous = found.get(condition_id)
                if previous is None or previous["_sport"] == "sports":
                    found[condition_id] = candidate
    keys = sorted(found, key=lambda k: (-found[k]["_volume"], k))
    if cap and cap > 0:
        keys = keys[:cap]
    # back to id order: the ranking decides WHICH markets, not their file order
    return [found[key] for key in sorted(keys)]


def normalize_market(market: dict, holders: Any, oi: Any, trades: Any,
                     threshold: float = WHALE_MIN_USD) -> dict | None:
    """Normalize one market and retain only threshold-meeting public records."""
    outcomes = [str(v) for v in _list(market.get("outcomes"))]
    prices = [_number(v) for v in _list(market.get("outcomePrices"))]
    if not outcomes or len(outcomes) != len(prices):
        raise ValueError(f"missing outcome prices for {market.get('conditionId')}")
    if holders is None:
        holders = []
    if not isinstance(holders, list) or not isinstance(trades, list):
        raise ValueError("malformed holders or trades response")

    by_index: dict[int, list[dict]] = {i: [] for i in range(len(outcomes))}
    for token in holders:
        for row in token.get("holders") or []:
            index = int(_number(row.get("outcomeIndex"), -1))
            if index not in by_index:
                continue
            shares = _number(row.get("amount"))
            current_value = shares * prices[index]
            wallet = _wallet(row)
            if wallet and current_value >= threshold:
                by_index[index].append({
                    "wallet": wallet,
                    "display": _display(row),
                    "shares": round(shares, 6),
                    "current_value_usd": round(current_value, 2),
                })

    recent = []
    for row in trades:
        size, price = _number(row.get("size")), _number(row.get("price"))
        wallet = _wallet(row)
        notional = size * price
        if wallet and notional >= threshold:
            recent.append({
                "wallet": wallet,
                "display": _display(row),
                "side": str(row.get("side") or ""),
                "size": round(size, 6),
                "price": round(price, 6),
                "notional_usd": round(notional, 2),
                "outcome": str(row.get("outcome") or ""),
                "ts": int(_number(row.get("timestamp"))),
            })
    recent.sort(key=lambda row: (-row["ts"], row["wallet"]))

    normalized_outcomes = []
    for index, outcome in enumerate(outcomes):
        top = sorted(by_index[index],
                     key=lambda row: (-row["current_value_usd"], row["wallet"]))
        normalized_outcomes.append({
            "outcome": outcome,
            "index": index,
            "price": round(prices[index], 6),
            "top_holders": top,
        })

    if oi is None:
        oi = []
    if not isinstance(oi, list):
        raise ValueError("malformed open-interest response")
    if not recent and not any(row["top_holders"] for row in normalized_outcomes):
        return None
    return {
        "condition_id": market["conditionId"],
        "title": str(market.get("question") or market.get("title") or ""),
        "event_slug": str(market.get("eventSlug") or ""),
        "sport": market["_sport"],
        "open_interest": round(_number(oi[0].get("value")), 2) if oi else 0.0,
        "outcomes": normalized_outcomes,
        "recent": recent,
    }


def capture(session: requests.Session | None = None, gamma_base: str = GAMMA,
            data_base: str = DATA, threshold: float = WHALE_MIN_USD,
            cap: int = MARKET_CAP) -> dict:
    session = session or requests.Session()
    markets = []
    for market in discover(session, gamma_base, threshold, cap):
        condition_id = market["conditionId"]
        normalized = normalize_market(
            market,
            _get(session, f"{data_base}/holders", market=condition_id, limit=LIMIT),
            _get(session, f"{data_base}/oi", market=condition_id),
            _get(session, f"{data_base}/trades", market=condition_id, limit=LIMIT),
            threshold,
        )
        if normalized:
            markets.append(normalized)
    markets.sort(key=lambda row: (row["sport"], -row["open_interest"],
                                  row["condition_id"]))
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "whale_min_usd": threshold,
        "discovery_limit_per_tag": LIMIT,
        "markets_examined": cap,
        "depth_note": ("the busiest markets by 24h volume are examined, not "
                       "every open market"),
        "valuation": "holder shares multiplied by current outcome price",
        "markets": markets,
    }


def publish(path: Path = OUT, **capture_args: Any) -> dict:
    """Replace the public snapshot only after the complete capture succeeds."""
    payload = capture(**capture_args)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return payload


def _selfcheck() -> int:
    # the retry paths below are asserted for behaviour, not for wall-clock
    real_sleep, time.sleep = time.sleep, lambda _s: None
    try:
        return _run_selfcheck()
    finally:
        time.sleep = real_sleep


def _run_selfcheck() -> int:
    market = {
        "conditionId": "0x1", "question": "Will New York win?",
        "eventSlug": "season", "_sport": "mlb",
        "volumeNum": 50000,
        "outcomes": '["Yes", "No"]', "outcomePrices": '["0.40", "0.60"]',
    }
    holders = [{"holders": [
        {"proxyWallet": "0xlarge", "amount": 30000, "name": "PublicName",
         "outcomeIndex": 0, "email": "must-not-escape@example.com"},
        {"proxyWallet": "0xsmall", "amount": 10, "outcomeIndex": 1},
    ]}]
    trades = [{"proxyWallet": "0xtrade", "size": 25000, "price": 0.5,
               "side": "BUY", "outcome": "Yes", "timestamp": 2,
               "pseudonym": "PublicAlias", "email": "private@example.com"}]
    got = normalize_market(market, holders, [{"value": 12345.678}], trades)
    assert got and got["sport"] == "mlb" and got["open_interest"] == 12345.68
    assert got["outcomes"][0]["price"] == 0.4
    assert got["outcomes"][0]["top_holders"][0]["current_value_usd"] == 12000
    assert got["recent"][0]["notional_usd"] == 12500
    assert "email" not in json.dumps(got).lower()

    class Response:
        def __init__(self, body, status=200, headers=None):
            self.body, self.status_code = body, status
            self.headers = headers or {}
        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code}", response=self)
        def json(self): return self.body

    class Session:
        def get(self, url, **kwargs):
            sport = kwargs["params"].get("tag_slug")
            body = [{"markets": [market]}] if sport in ("sports", "mlb") else []
            return Response(body)

    class FailedSession(Session):
        def get(self, url, **kwargs):
            if url.endswith("/events"):
                return super().get(url, **kwargs)
            raise requests.ConnectionError("forced selfcheck failure")

    class Throttled:
        """429 twice, then answer — the shape the live capture actually hit."""
        def __init__(self): self.calls = 0
        def get(self, url, **kwargs):
            self.calls += 1
            if self.calls <= 2:
                return Response([], status=429, headers={"Retry-After": "0"})
            return Response([{"markets": [market]}])

    throttled = Throttled()
    assert _get(throttled, "https://fixture/events") == [{"markets": [market]}]
    assert throttled.calls == 3, throttled.calls

    class Gone:
        """a 404 is not transient and must not burn four retries"""
        def __init__(self): self.calls = 0
        def get(self, url, **kwargs):
            self.calls += 1
            return Response(None, status=404)

    class Flaky:
        """408 then 200 — the second failure the live capture actually hit."""
        def __init__(self): self.calls = 0
        def get(self, url, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return Response(None, status=408)
            return Response([{"markets": [market]}])

    flaky = Flaky()
    assert _get(flaky, "https://fixture/events") == [{"markets": [market]}]
    assert flaky.calls == 2, flaky.calls

    class Dropped:
        """a dropped connection costs one retry, not the capture"""
        def __init__(self): self.calls = 0
        def get(self, url, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise requests.ConnectionError("reset by peer")
            return Response([{"markets": [market]}])

    dropped = Dropped()
    assert _get(dropped, "https://fixture/events") == [{"markets": [market]}]
    assert dropped.calls == 2, dropped.calls

    gone = Gone()
    try:
        _get(gone, "https://fixture/holders")
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("404 should raise")
    assert gone.calls == 1, gone.calls

    deduped = discover(Session(), "https://fixture")
    assert len(deduped) == 1 and deduped[0]["_sport"] == "mlb", deduped

    class Many:
        """three markets, ascending volume, ids deliberately anti-correlated"""
        def get(self, url, **kwargs):
            if kwargs["params"].get("tag_slug") != "mlb":
                return Response([])
            return Response([{"markets": [
                dict(market, conditionId="0xc", volumeNum=90000),
                dict(market, conditionId="0xb", volumeNum=70000),
                dict(market, conditionId="0xa", volumeNum=50000),
            ]}])

    top2 = discover(Many(), "https://fixture", cap=2)
    assert [m["conditionId"] for m in top2] == ["0xb", "0xc"], top2
    assert discover(Many(), "https://fixture", cap=0).__len__() == 3
    page = Path("site/public/whales.html").read_text(encoding="utf-8")
    assert not BANNED.search(" ".join(READER_COPY) + " " + page)

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "whales.json"
        path.write_bytes(b"previous-complete-snapshot")
        try:
            publish(path, session=FailedSession(), data_base="https://fixture")
        except (KeyError, requests.RequestException, ValueError):
            pass
        assert path.read_bytes() == b"previous-complete-snapshot"

    print("whales.selfcheck: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--top", type=int, default=MARKET_CAP,
                        help="how many markets to examine, busiest first")
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        return _selfcheck()
    payload = publish(args.out, cap=args.top)
    print(f"{len(payload['markets'])} qualifying markets -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
