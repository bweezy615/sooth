"""The contract every sport adapter implements.

Adding a sport means implementing this interface and nothing else. The
backtester, the calibrator, the commitment scheme and the site renderer are
all sport-agnostic and consume only these methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..schema import Event, Line, Result, Sport


class SportAdapter(ABC):
    """Normalises one sport's messy public data into the unified schema."""

    sport: Sport

    # -- historical: used for training and backtesting -----------------------

    @abstractmethod
    def load_history(self, start_season: int, end_season: int) -> list[Event]:
        """Every completed contest in the range, oldest first."""

    @abstractmethod
    def load_results(self, events: list[Event]) -> dict[str, Result]:
        """Settled outcomes keyed by event_id. Missing events are simply absent."""

    @abstractmethod
    def load_historical_lines(self, events: list[Event]) -> list[Line]:
        """Market quotes for backtesting.

        Implementations MUST set ``is_closing`` truthfully. If a source does
        not distinguish opening from closing, ``is_closing`` stays False and
        the line is excluded from closing-line-value analysis. Guessing here
        silently corrupts every CLV number downstream.
        """

    # -- live: used in-season --------------------------------------------------

    @abstractmethod
    def upcoming(self, now: datetime) -> list[Event]:
        """Contests that have not started yet and are open for prediction."""

    @abstractmethod
    def current_lines(self, events: list[Event]) -> list[Line]:
        """Latest available market quotes for the given events."""

    # -- features --------------------------------------------------------------

    @abstractmethod
    def feature_frame(self, events: list[Event], asof: datetime):
        """Model features for ``events``, computed using ONLY information
        available at ``asof``.

        This is the leakage boundary and the single most important method in
        the codebase. A feature that quietly includes post-game information
        (final weather readings, final injury status, a line that was
        overwritten after kickoff) produces a backtest that looks excellent
        and a live model that loses. Every implementation must be able to
        justify, per column, that the value was knowable at ``asof``.
        """
