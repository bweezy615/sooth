"""The board build records the account balance it was already told.

Two readings of the Odds API account taken on 2026-08-28 disagreed by a factor
of 26: a shell `curl` reported 113 credits left, while `props.json` — written
by CI that morning — recorded 3,008. Both were true. They were different API
keys on different plans, and nothing in the repo recorded enough to tell them
apart, because the only balance series came from one workflow and carried
`remaining` without `used`.

`remaining` alone cannot answer the question that matters: 3,008 left is a
comfortable month on a 20,000 plan and an impossibility on a 500 one. Recording
`used` alongside it makes the plan size fall out of the pair, so a falling
balance can be read as a cycle draining or a pool that never refills without
anyone having to log in anywhere. Both headers ride along on odds calls the
board already pays for, so this costs nothing.
"""
import engine.lines as lines


class _Resp:
    def __init__(self, headers, status=200, payload=None):
        self.headers = headers
        self.status_code = status
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, resp):
        self._resp = resp

    def get(self, *a, **k):
        return self._resp


def _collect(monkeypatch, headers, status=200):
    monkeypatch.setattr(lines, "load_key", lambda: "test-key")
    monkeypatch.setattr(lines, "active_sports",
                        lambda k, s: set(lines.SPORTS))
    resp = _Resp(headers, status=status)
    monkeypatch.setattr(lines.requests, "Session", lambda: _FakeSession(resp))
    return lines.collect(dry_run=True)


def test_balance_is_recorded_from_the_call_the_board_already_paid_for(
        monkeypatch):
    doc = _collect(monkeypatch, {"x-requests-last": "5",
                                 "x-requests-remaining": "3008",
                                 "x-requests-used": "16992"})
    assert doc["credits_remaining"] == 3008
    assert doc["credits_used"] == 16992
    # The pair is the point: it names the plan without a second request.
    assert doc["credits_remaining"] + doc["credits_used"] == 20000


def test_missing_headers_read_as_unknown_not_as_empty(monkeypatch):
    """-1, never 0. An unreported balance must not look like an exhausted one."""
    doc = _collect(monkeypatch, {"x-requests-last": "5"})
    assert doc["credits_remaining"] == -1
    assert doc["credits_used"] == -1


def test_garbage_headers_do_not_crash_the_board_build(monkeypatch):
    doc = _collect(monkeypatch, {"x-requests-last": "5",
                                 "x-requests-remaining": "",
                                 "x-requests-used": "not-a-number"})
    assert doc["credits_remaining"] == -1
    assert doc["credits_used"] == -1


def test_balance_is_recorded_even_when_the_sport_call_fails(monkeypatch):
    """A 429 still carries the balance, and that is exactly when it matters."""
    doc = _collect(monkeypatch, {"x-requests-last": "0",
                                 "x-requests-remaining": "0",
                                 "x-requests-used": "500"}, status=429)
    assert doc["credits_remaining"] == 0
    assert doc["credits_used"] == 500
