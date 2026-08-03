"""Sport-agnostic schema.

One engine serves every sport. Each sport adapter normalises its source data
into these structures and nothing downstream knows what sport it is looking at.

Design notes
------------
Two-sided contests (NFL, NBA, MLB, NHL, EPL, UFC, tennis) map directly onto
``side_a``/``side_b``. Field events (F1) are expanded by their adapter into
one row per entrant against the field, so the same probability machinery and
the same grading code apply without special-casing.

Every timestamp is UTC. Every probability is a calibrated probability of the
stated ``selection`` happening, not a confidence score, not an opinion.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any


class Sport(str, Enum):
    NFL = "nfl"
    NBA = "nba"
    MLB = "mlb"
    NHL = "nhl"
    EPL = "epl"
    UFC = "ufc"
    F1 = "f1"
    TENNIS = "tennis"
    CRICKET = "cricket"


class Market(str, Enum):
    MONEYLINE = "moneyline"
    SPREAD = "spread"
    TOTAL = "total"


class Status(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    FINAL = "final"
    CANCELLED = "cancelled"


@dataclass
class Event:
    """A single contest we can predict and later grade."""

    event_id: str
    sport: Sport
    season: int
    stage: str  # week number, round name, matchday - sport decides
    start_time: datetime  # UTC kickoff/first-whistle
    side_a: str  # home / favourite-by-position / fighter A
    side_b: str  # away / challenger / fighter B
    neutral_site: bool = False
    status: Status = Status.SCHEDULED
    venue: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sport"] = self.sport.value
        d["status"] = self.status.value
        d["start_time"] = self.start_time.isoformat()
        return d


@dataclass
class Line:
    """A market quote observed at a point in time.

    ``captured_at`` is mandatory and load-bearing. A line without a capture
    timestamp is unusable for closing-line value, because we cannot prove we
    predicted before the market moved. nflverse's ``spread_line`` is
    overwritten in place as lines move and therefore must NEVER be stored as
    a closing line - see adapters/nfl.py.
    """

    event_id: str
    market: Market
    selection: str  # side_a / side_b / "over" / "under"
    line: float | None  # spread or total number; None for moneyline
    price: int  # American odds
    book: str
    captured_at: datetime
    is_closing: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["market"] = self.market.value
        d["captured_at"] = self.captured_at.isoformat()
        return d


@dataclass
class Prediction:
    """Our forecast. Written once, never edited.

    ``probability`` is a calibrated probability, validated by reliability
    curve and Brier score before a sport is allowed to ship as Live.
    """

    event_id: str
    sport: Sport
    market: Market
    selection: str
    line: float | None
    probability: float
    model_version: str
    created_at: datetime
    # the market quote we saw when we predicted - the CLV baseline
    reference_price: int | None = None
    reference_line: float | None = None
    rationale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sport"] = self.sport.value
        d["market"] = self.market.value
        d["created_at"] = self.created_at.isoformat()
        return d


@dataclass
class Result:
    """Settled outcome. The grading half of the public record."""

    event_id: str
    score_a: float
    score_b: float
    settled_at: datetime

    @property
    def margin(self) -> float:
        """Positive when side_a won."""
        return self.score_a - self.score_b

    @property
    def total(self) -> float:
        return self.score_a + self.score_b

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["settled_at"] = self.settled_at.isoformat()
        d["margin"] = self.margin
        d["total"] = self.total
        return d


# --------------------------------------------------------------------------
# Odds helpers - shared by every sport
# --------------------------------------------------------------------------

def american_to_prob(price: int) -> float:
    """Convert American odds to implied probability (vig included)."""
    if price < 0:
        return -price / (-price + 100.0)
    return 100.0 / (price + 100.0)


def prob_to_american(prob: float) -> int:
    """Inverse of american_to_prob, rounded to a whole cent."""
    if not 0.0 < prob < 1.0:
        raise ValueError(f"probability out of range: {prob}")
    if prob >= 0.5:
        return int(round(-100.0 * prob / (1.0 - prob)))
    return int(round(100.0 * (1.0 - prob) / prob))


def devig(prob_a: float, prob_b: float) -> tuple[float, float]:
    """Remove bookmaker margin proportionally.

    The raw implied probabilities of both sides sum to >1; the excess is the
    vig. Proportional (multiplicative) de-vigging is the standard baseline.
    We compare our model against the DE-VIGGED market, because beating a
    vigged line is trivially easy and meaningless.
    """
    total = prob_a + prob_b
    if total <= 0:
        raise ValueError("degenerate market")
    return prob_a / total, prob_b / total
